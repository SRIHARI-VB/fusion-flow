"""One-shot, re-runnable live demonstration of Phase 5's WhatsApp
end-to-end automation pieces working together, against the real
database — not a seed script, mirrors `demo_phase4_proof_of_concept.py`'s
shape and conventions exactly.

Builds one workflow for the "Srihari" tenant:

    whatsapp.interactive_reply_received (customer tapped a button)
      -> condition.multi_branch on interactive.id
           "confirm_order" -> whatsapp.send_template (UTILITY: order_confirmation)
           "see_offers"    -> whatsapp.send_template (MARKETING: weekend_sale)
           default          -> send_whatsapp_message (plain session text reply)

This exercises, in one real published/simulated workflow:
  - the new whatsapp.interactive_reply_received trigger (Part C)
  - condition.multi_branch keyed on a real interactive-reply payload shape
  - whatsapp.send_template for BOTH a utility and a marketing category
    template (Part A/B/C together - the send node cross-checks the
    variable count against the local WhatsAppTemplate catalog row before
    calling Meta)
  - the pre-existing send_whatsapp_message node for a normal session
    message, proving the new pieces compose with what already shipped in
    earlier phases rather than replacing it

Requires `seed_workflow_node_templates.py`'s catalog rows are NOT needed
here (this demo uses the dedicated WhatsApp node types directly, not the
generic-executor + template layer - see this phase's plan section for why
WhatsApp's primary nodes are dedicated types). It DOES need at least the
two templates `sync_from_meta`'s stub returns (order_confirmation/
weekend_sale) to exist in the local catalog - this script syncs them
itself if missing.

Usage:
    python scripts/demo_phase5_whatsapp_proof_of_concept.py
"""

from __future__ import annotations

import asyncio
import uuid

from fusionflow.db import models as _models  # noqa: F401 - ORM registration side effect
from fusionflow.db.session import async_session_factory, set_tenant_context
from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorType
from fusionflow.modules.connectors.whatsapp import service as whatsapp_service
from fusionflow.modules.tenancy.models import Business, Membership
from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.models import Workflow, WorkflowRunStep
from sqlalchemy import delete, select

SRIHARI_BUSINESS_KEY = "Srihari"
DEMO_WORKFLOW_NAME = "Phase 5 WhatsApp proof of concept"


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {"id": node_id, "type": node_type, "data": {"nodeType": node_type, "config": config or {}}}


def _edge(edge_id: str, source: str, target: str, source_handle: str | None = None) -> dict:
    edge: dict = {"id": edge_id, "source": source, "target": target}
    if source_handle is not None:
        edge["sourceHandle"] = source_handle
    return edge


def build_graph(whatsapp_instance_id: uuid.UUID) -> dict:
    instance_id = str(whatsapp_instance_id)
    return {
        "nodes": [
            _node("trigger", "whatsapp.interactive_reply_received"),
            _node(
                "classify",
                "condition.multi_branch",
                {
                    "cases": [
                        {"label": "confirm", "field_path": "trigger.interactive.id", "value": "confirm_order"},
                        {"label": "offers", "field_path": "trigger.interactive.id", "value": "see_offers"},
                    ],
                    "default_label": "other",
                },
            ),
            _node(
                "send_confirmation",
                "whatsapp.send_template",
                {
                    "connector_instance_id": instance_id,
                    "to": "{{trigger.from}}",
                    "template_name": "order_confirmation",
                    "language_code": "en_US",
                    "body_variables": ["{{trigger.from}}", "#1234"],
                },
            ),
            _node(
                "send_promo",
                "whatsapp.send_template",
                {
                    "connector_instance_id": instance_id,
                    "to": "{{trigger.from}}",
                    "template_name": "weekend_sale",
                    "language_code": "en_US",
                    "body_variables": ["{{trigger.from}}"],
                },
            ),
            _node(
                "send_fallback",
                "send_whatsapp_message",
                {
                    "connector_instance_id": instance_id,
                    "to": "{{trigger.from}}",
                    "body": "Thanks for reaching out! How can we help?",
                },
            ),
        ],
        "edges": [
            _edge("e1", "trigger", "classify"),
            _edge("e2", "classify", "send_confirmation", source_handle="confirm"),
            _edge("e3", "classify", "send_promo", source_handle="offers"),
            _edge("e4", "classify", "send_fallback", source_handle="other"),
        ],
    }


async def main() -> None:
    async with async_session_factory() as session:
        business = (
            await session.execute(select(Business).where(Business.name == SRIHARI_BUSINESS_KEY))
        ).scalar_one()
        await set_tenant_context(session, business.id)
        membership = (
            await session.execute(select(Membership).where(Membership.business_id == business.id))
        ).scalars().first()
        user_id = membership.user_id

        whatsapp_type = (
            await session.execute(select(ConnectorType).where(ConnectorType.key == "whatsapp"))
        ).scalar_one()
        instance = (
            await session.execute(
                select(ConnectorInstance).where(
                    ConnectorInstance.tenant_id == business.id,
                    ConnectorInstance.connector_type_id == whatsapp_type.id,
                )
            )
        ).scalars().first()
        print(f"using connector instance {instance.id}")

        # Ensure the two templates this demo references exist locally
        # (idempotent - sync_from_meta upserts by name+language).
        await whatsapp_service.sync_from_meta(session, tenant_id=business.id, connector_instance_id=instance.id)
        await session.commit()
        await set_tenant_context(session, business.id)
        print("synced templates:", sorted(t.name for t in await whatsapp_service.list_templates(
            session, tenant_id=business.id, connector_instance_id=instance.id
        )))

        await set_tenant_context(session, business.id)
        await session.execute(
            delete(Workflow).where(Workflow.tenant_id == business.id, Workflow.name == DEMO_WORKFLOW_NAME)
        )
        await session.commit()
        await set_tenant_context(session, business.id)

        workflow = await workflows_service.create_workflow(
            session, tenant_id=business.id, name=DEMO_WORKFLOW_NAME, graph=build_graph(instance.id), created_by=user_id,
        )
        await session.commit()
        print(f"created workflow {workflow.id}")

        await set_tenant_context(session, business.id)
        _, version, result = await workflows_service.publish_workflow(session, workflow, published_by=user_id)
        await session.commit()
        print(f"publish valid={not result.has_errors}")
        for issue in result.issues:
            print(f"  [{issue.severity}] {issue.rule} ({issue.node_id}): {issue.message}")
        if result.has_errors:
            print("ABORTING - fix validation errors before simulating")
            return

        scenarios = [
            ("customer confirms order", {"from": "15551234567", "interactive": {"id": "confirm_order", "title": "Confirm"}}),
            ("customer wants to see offers", {"from": "15557654321", "interactive": {"id": "see_offers", "title": "See offers"}}),
            ("customer taps something else", {"from": "15559999999", "interactive": {"id": "cancel", "title": "Cancel"}}),
        ]

        for label, payload in scenarios:
            print(f"\n--- scenario: {label} ---")
            await set_tenant_context(session, business.id)
            run = await workflows_service.simulate_workflow(session, workflow, payload=payload)
            run_status = run.status
            run_id = run.id
            steps = (
                await session.execute(
                    select(WorkflowRunStep).where(WorkflowRunStep.workflow_run_id == run_id).order_by(WorkflowRunStep.started_at)
                )
            ).scalars().all()
            printable = [(s.node_id, s.node_type, s.status.value, s.error) for s in steps]
            await session.commit()
            print(f"run status: {run_status}")
            for node_id, node_type, status_value, error in printable:
                print(f"  {node_id} [{node_type}] -> {status_value}")
                if error:
                    print(f"      error: {error}")


if __name__ == "__main__":
    asyncio.run(main())
