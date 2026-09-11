"""One-shot, re-runnable live demonstration of Phase 8's pause/resume engine
and conversational ordering, against the real database - mirrors
`demo_phase6_module_query_proof_of_concept.py`'s shape and conventions.

Builds one workflow for the "Srihari" tenant:

    whatsapp.message_received (customer texts "Hi")
      -> whatsapp.find_or_create_customer (Phase 6)
      -> whatsapp.ask_question ("What size?") -> SUSPENDS
      -> whatsapp.ask_question ("What color?") -> SUSPENDS
      -> orders.create_from_conversation (COD, line item names the color)

This exercises, against the real database, in one real published workflow:
  - a run genuinely suspending twice in a row (RunStatus.WAITING persisted,
    `waiting_frontier`/`waiting_variables`/`waiting_expires_at` all real rows,
    not just asserted in an offline unit test)
  - `run_loop.resume_run` continuing the SAME run from exactly the right
    point, with each reply merged into the run's variable context
  - `orders.create_from_conversation` creating a real, workflow-stamped
    Order row (`source="workflow"`) referencing the captured color

Usage:
    python scripts/demo_phase8_conversational_ordering_proof_of_concept.py
"""

from __future__ import annotations

import asyncio
import uuid

from fusionflow.db import models as _models  # noqa: F401 - ORM registration side effect
from fusionflow.db.session import async_session_factory, set_tenant_context
from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorType
from fusionflow.modules.orders.models import Order
from fusionflow.modules.tenancy.models import Business, Membership
from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.run_loop import resume_run
from fusionflow.modules.workflows.engine.template_resolution import resolve_node_templates
from fusionflow.modules.workflows.models import RunStatus, Workflow
from sqlalchemy import delete, select

SRIHARI_BUSINESS_KEY = "Srihari"
DEMO_WORKFLOW_NAME = "Phase 8 conversational ordering proof of concept"
DEMO_PHONE = "15550002222"


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {"id": node_id, "type": node_type, "data": {"nodeType": node_type, "config": config or {}}}


def _edge(edge_id: str, source: str, target: str) -> dict:
    return {"id": edge_id, "source": source, "target": target}


def build_graph(whatsapp_instance_id: uuid.UUID) -> dict:
    instance_id = str(whatsapp_instance_id)
    return {
        "nodes": [
            _node("trigger", "whatsapp.message_received"),
            _node("find_customer", "whatsapp.find_or_create_customer", {"phone": "{{trigger.from}}"}),
            _node(
                "ask_size",
                "whatsapp.ask_question",
                {
                    "connector_instance_id": instance_id,
                    "to": "{{trigger.from}}",
                    "input_type": "text",
                    "question": "What size would you like?",
                },
            ),
            _node(
                "ask_color",
                "whatsapp.ask_question",
                {
                    "connector_instance_id": instance_id,
                    "to": "{{trigger.from}}",
                    "input_type": "text",
                    "question": "What color would you like?",
                },
            ),
            _node(
                "create_order",
                "orders.create_from_conversation",
                {
                    "customer_id": "{{find_customer.customer.id}}",
                    "line_items": [
                        {"name": "Demo T-Shirt ({{ask_color.reply}}, size {{ask_size.reply}})", "quantity": 1, "price": "499.00"}
                    ],
                    "currency": "INR",
                    "payment_method": "cod",
                },
            ),
        ],
        "edges": [
            _edge("e1", "trigger", "find_customer"),
            _edge("e2", "find_customer", "ask_size"),
            _edge("e3", "ask_size", "ask_color"),
            _edge("e4", "ask_color", "create_order"),
        ],
    }


async def _reload_graph(session, workflow: Workflow) -> WorkflowGraph:
    version = await workflows_service.get_latest_version(session, workflow.id)
    compiled = await resolve_node_templates(session, version.graph)
    return WorkflowGraph.from_json(compiled)


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

        # --- Reset demo data (idempotent re-run) -----------------------------
        await set_tenant_context(session, business.id)
        await session.execute(
            delete(Order).where(Order.tenant_id == business.id, Order.source == "workflow")
        )
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

        # --- Turn 1: customer texts "Hi" -> suspends at ask_size -------------
        print("\n--- turn 1: customer texts 'Hi' ---")
        await set_tenant_context(session, business.id)
        run = await workflows_service.simulate_workflow(
            session, workflow, payload={"from": DEMO_PHONE, "message_id": "wamid.p8.1", "type": "text", "text": "Hi"}
        )
        await session.commit()
        print(f"run status: {run.status.value}")
        print(f"  waiting_node_id={run.waiting_node_id} correlation_key={run.waiting_correlation_key}")
        print(f"  waiting_expires_at={run.waiting_expires_at}")
        assert run.status == RunStatus.WAITING and run.waiting_node_id == "ask_size"

        # --- Turn 2: customer replies "Large" -> resumes, suspends at ask_color
        print("\n--- turn 2: customer replies 'Large' ---")
        await set_tenant_context(session, business.id)
        graph = await _reload_graph(session, workflow)
        run = await resume_run(session, run, graph, reply_payload={"text": "Large"})
        await session.commit()
        print(f"run status: {run.status.value}")
        print(f"  waiting_node_id={run.waiting_node_id}")
        assert run.status == RunStatus.WAITING and run.waiting_node_id == "ask_color"

        # --- Turn 3: customer replies "Blue" -> resumes, creates the order ---
        print("\n--- turn 3: customer replies 'Blue' ---")
        await set_tenant_context(session, business.id)
        graph = await _reload_graph(session, workflow)
        run = await resume_run(session, run, graph, reply_payload={"text": "Blue"})
        await session.commit()
        print(f"run status: {run.status.value}")
        assert run.status == RunStatus.COMPLETED

        await set_tenant_context(session, business.id)
        order = (
            await session.execute(
                select(Order).where(Order.tenant_id == business.id, Order.source == "workflow")
            )
        ).scalars().first()
        print(f"\ncreated order {order.id}: source={order.source} payment_method={order.payment_method}")
        print(f"  line_items={order.line_items}")
        print(f"  created_by_workflow_run_id={order.created_by_workflow_run_id}")
        assert order.created_by_workflow_run_id == run.id
        assert "Blue" in order.line_items[0]["name"] and "Large" in order.line_items[0]["name"]

        print("\nAll assertions passed.")


if __name__ == "__main__":
    asyncio.run(main())
