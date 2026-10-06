"""Guarded clinic upgrade: patient contact details and recoverable booking links.

Default is read-only. --apply publishes a new immutable workflow version,
adds optional appointment fields and links old records using successful run
steps. It does not execute workflows, send messages or cancel appointments.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import json
import uuid

from sqlalchemy import select, text

from scripts.repair_clinic_instagram_workflow import RepairError, repair_workflow

NAME_STEPS = {
    "ask-patient-name-consult": "save-patient-name-consult",
    "ask-patient-name-treatment": "save-patient-name-treatment",
    "collect-patient-name-ortho": "update-customer-name-ortho",
    "collect-patient-name-other": "update-customer-name-other",
    "collect-patient-name-emergency": "update-customer-name-emergency",
}
CALENDAR_STEPS = {
    "upsert-appointment-online": "book-calendar-event-online",
    "upsert-appointment-offline": "book-calendar-event-offline",
    "upsert-appointment-offline-viaask": "book-calendar-event-offline-viaask",
}
NEW_FIELDS = {
    "customer_phone": "Patient phone number",
    "calendar_event_id": "Calendar event ID",
    "calendar_connector_instance_id": "Calendar connection ID",
}


def patient_details_graph(original: dict) -> dict:
    graph = deepcopy(original)
    nodes = {n["id"]: n for n in graph["nodes"]}
    if len(nodes) != len(graph["nodes"]):
        raise RepairError("Duplicate node IDs")

    def insert_before(target, new_node):
        if new_node["id"] in nodes:
            if nodes[new_node["id"]] != new_node:
                raise RepairError(f"Unexpected existing node: {new_node['id']}")
            return
        incoming = [e for e in graph["edges"] if e["target"] == target]
        if not incoming:
            raise RepairError(f"No incoming edge for {target}")
        for edge in incoming:
            edge["target"] = new_node["id"]
        graph["edges"].append({"id": f"e-{new_node['id']}-continue", "source": new_node["id"], "target": target})
        graph["nodes"].append(new_node)
        nodes[new_node["id"]] = new_node

    for ask_id, save_id in NAME_STEPS.items():
        ask, save = nodes[ask_id], nodes[save_id]
        if ask["data"]["nodeType"] != "instagram.collect_text" or save["data"]["config"]["module"] != "customers":
            raise RepairError(f"Unexpected patient-name branch: {ask_id}")
        ask["data"]["config"]["question"] = "What is the patient's full name?"
        phone = deepcopy(ask)
        phone["id"] = ask_id.replace("name", "phone")
        phone["data"]["label"] = ask["data"]["label"].replace("Name", "Phone Number")
        phone["data"]["config"]["question"] = "What is the patient's phone number (including country code)?"
        phone["position"]["x"] += 260
        phone_save = deepcopy(save)
        phone_save["id"] = save_id.replace("name", "phone")
        phone_save["data"]["label"] = save["data"]["label"].replace("Name", "Phone Number")
        phone_save["data"]["config"]["fields"] = {"phone": "{{" + phone["id"] + ".reply}}"}
        phone_save["position"]["x"] += 520
        if phone["id"] not in nodes:
            outgoing = [e for e in graph["edges"] if e["source"] == save_id]
            if len(outgoing) != 1 or outgoing[0].get("sourceHandle"):
                raise RepairError(f"Unexpected continuation of {save_id}")
            outgoing[0]["source"] = phone_save["id"]
            graph["edges"].extend([
                {"id": f"e-{save_id}-phone", "source": save_id, "target": phone["id"]},
                {"id": f"e-{phone['id']}-save", "source": phone["id"], "target": phone_save["id"]},
            ])
            graph["nodes"].extend([phone, phone_save])
            nodes.update({phone["id"]: phone, phone_save["id"]: phone_save})
        elif nodes[phone["id"]] != phone or nodes.get(phone_save["id"]) != phone_save:
            raise RepairError("Patient phone steps have changed")

    bookings = [n for n in list(graph["nodes"]) if n["data"].get("config", {}).get("module") == "appointment"
                and n["data"]["nodeType"] == "records.upsert" and n["data"]["config"].get("operation") == "create"]
    if len(bookings) != 18:
        raise RepairError("Expected all 18 clinic appointment creation paths")
    for booking in bookings:
        fields = booking["data"]["config"]["fields"]
        calendar_id = CALENDAR_STEPS.get(booking["id"])
        target = nodes[calendar_id] if calendar_id else booking
        lookup_id = "patient-details-" + booking["id"]
        lookup = {"id": lookup_id, "type": "action", "position": {
            "x": target["position"]["x"] - 200, "y": target["position"]["y"],
        }, "data": {"label": "Read Current Patient Details", "nodeType": "module.get", "config": {
            "module": "customers", "item_id": fields["customer_id"],
        }}}
        insert_before(target["id"], lookup)
        old_name = "{{find-or-create-customer-pb.customer.name}}"
        name = "{{" + lookup_id + ".item.name}}"
        phone = "{{" + lookup_id + ".item.phone}}"
        fields["customer_name"] = name
        fields["customer_phone"] = phone
        fields["service"] = fields["service"].replace(old_name, name)
        if calendar_id:
            config = target["data"]["config"]
            fields["calendar_event_id"] = "{{" + calendar_id + ".id}}"
            fields["calendar_connector_instance_id"] = config["connector_instance_id"]
            description = config["params"]["description"].replace(old_name, name)
            if "Phone: " not in description:
                description += "\nPhone: " + phone
            config["params"]["description"] = description
    return graph


async def recover_booking_links(session, *, tenant_id, workflow_id, apply=False):
    """Exact record IDs from successful create steps; never fuzzy-match PHI."""
    from fusionflow.modules.business_objects.models import ObjectRecord, ObjectTypeDefinition
    from fusionflow.modules.customers.models import Customer
    from fusionflow.modules.workflows.engine.appointment_links import booking_evidence

    records = (await session.execute(select(ObjectRecord).join(ObjectTypeDefinition).where(
        ObjectRecord.tenant_id == tenant_id, ObjectTypeDefinition.key == "appointment",
    ))).scalars().all()
    linked = unresolved = 0
    for record in records:
        customer = await session.get(Customer, record.customer_id) if record.customer_id else None
        if not customer or not customer.external_ref:
            continue
        evidence = await booking_evidence(session, record, sender=customer.external_ref, workflow_id=workflow_id)
        if evidence is None:
            unresolved += 1
            continue
        run_id, payload = evidence
        if record.created_by_run_id != run_id or payload != record.payload:
            linked += 1
            if apply:
                record.created_by_run_id = run_id
                record.payload = payload
    return {"booking_links_recovered": linked, "unresolved_booking_links": unresolved}


async def upgrade(session, *, tenant_id, workflow_id, actor_email, expected_version, apply=False):
    from fusionflow.modules.business_objects import service
    from fusionflow.modules.business_objects.schemas import ObjectFieldDefinitionCreate
    from fusionflow.modules.custom_fields.models import FieldType

    # Verify workflow version and permissions before any writes.
    report = await repair_workflow(session, tenant_id=tenant_id, workflow_id=workflow_id,
        actor_email=actor_email, expected_version=expected_version, apply=apply, graph_transform=patient_details_graph)
    kind = await service.get_object_type_by_key(session, tenant_id=tenant_id, key="appointment")
    if kind is None:
        raise RepairError("Appointment object type missing")
    existing = {f.key: f for f in await service.list_field_definitions(session, tenant_id=tenant_id, object_type_id=kind.id)}
    for key, label in NEW_FIELDS.items():
        if key in existing:
            if existing[key].field_type != FieldType.TEXT or existing[key].required:
                raise RepairError(f"Unexpected appointment field definition: {key}")
        elif apply:
            await service.create_field_definition(session, tenant_id=tenant_id, object_type_id=kind.id,
                payload=ObjectFieldDefinitionCreate(key=key, label=label, field_type=FieldType.TEXT, sort_order=100))
    report["new_fields"] = [k for k in NEW_FIELDS if k not in existing]
    report.update(await recover_booking_links(session, tenant_id=tenant_id, workflow_id=workflow_id, apply=apply))
    return report


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=uuid.UUID, required=True)
    parser.add_argument("--workflow-id", type=uuid.UUID, required=True)
    parser.add_argument("--actor-email", required=True)
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    from fusionflow.db import models as _models  # noqa: F401
    from fusionflow.db.session import async_session_factory, set_tenant_context
    async with async_session_factory() as session, session.begin():
        if not args.apply:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        await set_tenant_context(session, args.tenant_id)
        report = await upgrade(session, **vars(args))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
