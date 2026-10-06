"""Use current clinic settings in Clinic Info and Emergency Support.

Default is read-only. --apply publishes a new immutable workflow version;
it never executes the workflow or sends a message.
"""
from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import json
import uuid

from sqlalchemy import text

from scripts.repair_clinic_instagram_workflow import RepairError, repair_workflow


def contact_details_graph(original: dict) -> dict:
    graph = deepcopy(original)
    nodes = {n["id"]: n for n in graph["nodes"]}
    if len(nodes) != len(graph["nodes"]):
        raise RepairError("Duplicate node IDs")
    expected = {
        "business-settings-pb": "records.get_latest",
        "info-resolve-hours": "schedule.resolve_business_hours",
        "resolve-emergency-hours-msg": "schedule.resolve_business_hours",
        "collect-issue-support-emergency": "instagram.collect_text",
        "confirm-support-emergency": "connector.action",
        "reply-emergency-outhours-1": "connector.action",
        "info-reply-open": "connector.action",
        "info-reply-closed": "connector.action",
    }
    for node_id, kind in expected.items():
        if nodes.get(node_id, {}).get("data", {}).get("nodeType") != kind:
            raise RepairError(f"Unexpected or missing node: {node_id}")
    if nodes["business-settings-pb"]["data"]["config"] != {"module": "business_settings", "filters": {}}:
        raise RepairError("Clinic settings lookup has changed")

    def insert_before(target, new_node):
        node_id = new_node["id"]
        if node_id in nodes:
            incoming = [e for e in graph["edges"] if e["target"] == target]
            if (nodes[node_id] != new_node or len(incoming) != 1
                    or incoming[0]["source"] != node_id or incoming[0].get("sourceHandle")):
                raise RepairError(f"Unexpected existing lookup or bypass: {node_id}")
            return
        incoming = [e for e in graph["edges"] if e["target"] == target]
        if not incoming:
            raise RepairError(f"No incoming edge for {target}")
        for edge in incoming:
            edge["target"] = node_id
        graph["edges"].append({"id": f"e-{node_id}-continue", "source": node_id, "target": target})
        graph["nodes"].append(new_node)
        nodes[node_id] = new_node

    def settings_before(target, lookup_id):
        lookup = deepcopy(nodes["business-settings-pb"])
        lookup["id"] = lookup_id
        lookup["data"]["label"] = "Read Current Clinic Contact Details"
        lookup["position"] = deepcopy(nodes[target]["position"])
        lookup["position"]["x"] -= 240
        insert_before(target, lookup)
        return "{{" + lookup_id + ".item.payload.phone}}"

    # Both the Clinic Info button and typed questions enter this branch.
    # Previously the latter referenced an unexecuted postback-only lookup.
    settings_before("info-resolve-hours", "clinic-settings-info")
    for node_id in ("info-resolve-hours", "info-reply-open", "info-reply-closed"):
        config = nodes[node_id]["data"]["config"]
        nodes[node_id]["data"]["config"] = json.loads(json.dumps(config).replace(
            "business-settings-pb.item.payload.", "clinic-settings-info.item.payload.",
        ))
    for node_id in ("info-reply-open", "info-reply-closed"):
        if "{{clinic-settings-info.item.payload.phone}}" not in nodes[node_id]["data"]["config"]["params"]["text"]:
            raise RepairError(f"Clinic Info phone template missing: {node_id}")

    phone = settings_before("collect-issue-support-emergency", "clinic-settings-support-emergency")
    nodes["collect-issue-support-emergency"]["data"]["config"]["question"] = (
        f"Please call the clinic at {phone}.\n\n"
        "Please briefly describe the emergency so we can prioritize it."
    )
    # Refresh again after the patient's reply, which can arrive much later.
    phone = settings_before("confirm-support-emergency", "clinic-settings-support-confirm")
    nodes["confirm-support-emergency"]["data"]["config"]["params"]["text"] = (
        "We've flagged this as urgent and logged it for our team to reach out to you shortly. "
        f"If this is a medical emergency, please call the clinic at {phone}."
    )

    # The shared after-hours response also needs settings regardless of
    # whether it was reached from a message or a button. Resolve its date
    # here: its former template referenced a node that no longer exists.
    hours = deepcopy(nodes["resolve-emergency-hours-msg"])
    hours["id"] = "resolve-emergency-contact-hours"
    hours["data"]["label"] = "Resolve: Emergency Contact Hours"
    hours["position"] = deepcopy(nodes["reply-emergency-outhours-1"]["position"])
    hours["position"]["x"] -= 240
    hours["data"]["config"] = json.loads(json.dumps(hours["data"]["config"]).replace(
        "business-settings-msg.item.payload.", "clinic-settings-emergency-closed.item.payload.",
    ))
    insert_before("reply-emergency-outhours-1", hours)
    phone = settings_before(hours["id"], "clinic-settings-emergency-closed")
    nodes["reply-emergency-outhours-1"]["data"]["config"]["params"]["text"] = (
        "I'm sorry you're going through this. The clinic is closed right now "
        "(open Monday to Saturday, 10:00 AM - 8:30 PM). "
        f"Clinic phone: {phone}. Tap below and I'll arrange the earliest possible slot on "
        "{{resolve-emergency-contact-hours.next_open_date_display}} for you."
    )
    return graph


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
        report = await repair_workflow(session, **vars(args), graph_transform=contact_details_graph)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
