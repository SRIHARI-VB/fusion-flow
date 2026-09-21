"""One-shot, re-runnable live demonstration of Phase 6's module-query nodes
and new WhatsApp capabilities working together, against the real database -
mirrors `demo_phase5_whatsapp_proof_of_concept.py`'s shape and conventions.

Scenario, for the "Srihari" tenant: an inbound WhatsApp message arrives from
a phone number ->

    whatsapp.message_received (customer texts in)
      -> whatsapp.find_or_create_customer (looks up/creates a Customer by
         the sender's phone - Part D)
      -> module.list (orders, filtered by that customer's id + status,
         capped at 5 - Part B, dispatched through the OrdersQueryAdapter)
      -> whatsapp.send_message (content_type=template, utility
         "order_confirmation", using the found/created customer's name and
         the matched order count as the two body variables)

This exercises, in one real published/simulated workflow:
  - `whatsapp.find_or_create_customer` (Part D) actually finding an
    already-seeded customer by phone, and the customer-creation path when
    given an unrecognized number
  - `module.list` (Part B) dispatched through `OrdersQueryAdapter`,
    filtering by `customer_id` interpolated from a prior step's output
    (`{{find_customer.customer.id}}`) and by `status`, capped by the
    server-enforced pagination ceiling
  - `whatsapp.send_message`'s template content composing with
    `module.list`'s numeric `count` output as a template body variable -
    proving the module-query nodes and WhatsApp nodes compose in one real
    run

Also directly exercises (outside the simulated workflow, since both are
negative/boundary cases, not part of the "happy path" scenario) the two
deliberate CRUD exceptions from the Phase 6 plan:
  - `module.create` against `payments` fails cleanly (Payments has no
    create adapter method at all)
  - `module.update` against `orders` with a non-`status` field fails
    cleanly (Orders' update is restricted to `status` only)

Usage:
    python scripts/demo_phase6_module_query_proof_of_concept.py
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal

from fusionflow.db import models as _models  # noqa: F401 - ORM registration side effect
from fusionflow.db.session import async_session_factory, set_tenant_context
from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorType
from fusionflow.modules.customers import service as customers_service
from fusionflow.modules.customers.models import Customer
from fusionflow.modules.customers.schemas import CustomerCreate
from fusionflow.modules.orders import service as orders_service
from fusionflow.modules.orders.models import Order, OrderStatus
from fusionflow.modules.orders.schemas import OrderCreate
from fusionflow.modules.tenancy.models import Business, Membership
from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure
from fusionflow.modules.workflows.models import Workflow, WorkflowRunStep
from fusionflow.modules.workflows.nodes import module_create as module_create_node
from fusionflow.modules.workflows.nodes import module_update as module_update_node
from sqlalchemy import delete, select

SRIHARI_BUSINESS_KEY = "Srihari"
DEMO_WORKFLOW_NAME = "Phase 6 module-query proof of concept"
DEMO_PHONE = "15550001111"


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
                "recent_orders",
                "module.list",
                {
                    "module": "orders",
                    "filters": {"customer_id": "{{find_customer.customer.id}}", "status": "pending"},
                    "limit": 5,
                },
            ),
            _node(
                "send_confirmation",
                "whatsapp.send_message",
                {
                    "connector_instance_id": instance_id,
                    "to": "{{trigger.from}}",
                    "content": {
                        "content_type": "template",
                        "template_name": "order_confirmation",
                        "language_code": "en_US",
                        "body_variables": ["{{find_customer.customer.name}}", "{{recent_orders.count}}"],
                    },
                },
            ),
        ],
        "edges": [
            _edge("e1", "trigger", "find_customer"),
            _edge("e2", "find_customer", "recent_orders"),
            _edge("e3", "recent_orders", "send_confirmation"),
        ],
    }


async def _demo_crud_exceptions(session, tenant_id: uuid.UUID) -> None:
    """Live-exercises the two deliberate CRUD exceptions from the plan,
    outside the simulated workflow (negative cases, not the happy path)."""
    create_context = ExecutionContext(
        session=session,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="demo-create-payment",
        config={"module": "payments", "fields": {"amount": "10.00", "currency": "USD"}},
        variables={},
    )
    create_result = await module_create_node.ModuleCreateExecutor().execute(create_context)
    print(f"module.create(payments) -> {type(create_result).__name__}: "
          f"{create_result.error if isinstance(create_result, Failure) else create_result}")
    assert isinstance(create_result, Failure), "expected Payments to reject module.create"

    update_context = ExecutionContext(
        session=session,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="demo-update-order",
        config={"module": "orders", "item_id": str(uuid.uuid4()), "fields": {"total_amount": "999.00"}},
        variables={},
    )
    update_result = await module_update_node.ModuleUpdateExecutor().execute(update_context)
    print(f"module.update(orders, total_amount) -> {type(update_result).__name__}: "
          f"{update_result.error if isinstance(update_result, Failure) else update_result}")
    assert isinstance(update_result, Failure), "expected Orders to reject a non-status update field"


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

        # --- Reset demo data (idempotent re-run) ---------------------------
        await set_tenant_context(session, business.id)
        existing_customer = (
            await session.execute(select(Customer).where(Customer.tenant_id == business.id, Customer.phone == DEMO_PHONE))
        ).scalar_one_or_none()
        if existing_customer is not None:
            await session.execute(delete(Order).where(Order.customer_id == existing_customer.id))
            await session.delete(existing_customer)
        await session.execute(
            delete(Workflow).where(Workflow.tenant_id == business.id, Workflow.name == DEMO_WORKFLOW_NAME)
        )
        await session.commit()
        await set_tenant_context(session, business.id)

        # --- Seed a fresh customer + 3 orders -------------------------------
        customer = await customers_service.create_customer(
            session, business.id, CustomerCreate(name="Demo Customer", phone=DEMO_PHONE)
        )
        for status, amount in [
            (OrderStatus.PENDING, Decimal("49.99")),
            (OrderStatus.PENDING, Decimal("120.00")),
            (OrderStatus.FULFILLED, Decimal("15.00")),  # deliberately NOT "pending" - proves the filter excludes it
        ]:
            await orders_service.create_order(
                session, business.id, OrderCreate(customer_id=customer.id, status=status, total_amount=amount)
            )
        await session.commit()
        print(f"seeded customer {customer.id} with 3 orders (2 pending, 1 fulfilled)")

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

        # --- Scenario 1: known phone number (finds the seeded customer) ----
        print("\n--- scenario: known customer texts in ---")
        await set_tenant_context(session, business.id)
        run = await workflows_service.simulate_workflow(
            session, workflow, payload={"from": DEMO_PHONE, "message_id": "wamid.demo1", "type": "text", "text": {"body": "hi"}}
        )
        run_id = run.id
        run_status = run.status
        steps = (
            await session.execute(
                select(WorkflowRunStep).where(WorkflowRunStep.workflow_run_id == run_id).order_by(WorkflowRunStep.started_at)
            )
        ).scalars().all()
        printable = [(s.node_id, s.node_type, s.status.value, s.output, s.error) for s in steps]
        await session.commit()
        print(f"run status: {run_status}")
        for node_id, node_type, status_value, output, error in printable:
            print(f"  {node_id} [{node_type}] -> {status_value} output={output}")
            if error:
                print(f"      error: {error}")

        # --- Scenario 2: unknown phone number (creates a new customer) -----
        print("\n--- scenario: brand-new customer texts in ---")
        await set_tenant_context(session, business.id)
        new_phone = f"1555{uuid.uuid4().int % 10_000_000:07d}"
        run2 = await workflows_service.simulate_workflow(
            session, workflow, payload={"from": new_phone, "message_id": "wamid.demo2", "type": "text", "text": {"body": "hi"}}
        )
        steps2 = (
            await session.execute(
                select(WorkflowRunStep).where(WorkflowRunStep.workflow_run_id == run2.id).order_by(WorkflowRunStep.started_at)
            )
        ).scalars().all()
        printable2 = [(s.node_id, s.node_type, s.status.value, s.output, s.error) for s in steps2]
        await session.commit()
        print(f"run status: {run2.status}")
        for node_id, node_type, status_value, output, error in printable2:
            print(f"  {node_id} [{node_type}] -> {status_value} output={output}")
            if error:
                print(f"      error: {error}")

        # --- Deliberate CRUD exceptions (Payments create / Orders update) --
        print("\n--- deliberate CRUD exceptions ---")
        await set_tenant_context(session, business.id)
        await _demo_crud_exceptions(session, business.id)


if __name__ == "__main__":
    asyncio.run(main())
