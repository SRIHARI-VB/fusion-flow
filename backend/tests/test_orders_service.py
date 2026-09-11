"""Offline unit tests for `orders_service.create_order_from_workflow`
(Phase 8 Part C) and a regression check that `create_order` (used by real
checkout) is completely unaffected by its addition.

No Postgres required: `event_bus.publish_trigger_event` is monkeypatched
and a minimal fake session stands in for the real `AsyncSession` - neither
function does anything beyond `session.add`/`session.flush` plus the
event-bus call.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from fusionflow.modules.orders import service as orders_service
from fusionflow.modules.orders import workflow_adapter as orders_workflow_adapter  # noqa: F401 - registers the adapter
from fusionflow.modules.orders.schemas import OrderCreate
from fusionflow.modules.workflows.engine.module_registry import registry as module_query_registry
from fusionflow.modules.workflows.nodes import module_create as module_create_node
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure

pytestmark = pytest.mark.asyncio


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


async def test_create_order_from_workflow_stamps_workflow_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    published: dict[str, Any] = {}

    async def fake_publish_trigger_event(session, *, tenant_id, event_type, payload):
        published["tenant_id"] = tenant_id
        published["event_type"] = event_type
        published["payload"] = payload

    monkeypatch.setattr(orders_service.event_bus, "publish_trigger_event", fake_publish_trigger_event)

    session = _FakeSession()
    tenant_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    run_id = uuid.uuid4()
    payload = OrderCreate(customer_id=customer_id, total_amount=Decimal("42.50"), currency="USD", line_items=[])

    order = await orders_service.create_order_from_workflow(
        session, tenant_id, payload, workflow_run_id=run_id, payment_method="prepaid"
    )

    assert order in session.added
    assert order.source == "workflow"
    assert order.created_by_workflow_run_id == run_id
    assert order.payment_method == "prepaid"
    assert order.tenant_id == tenant_id
    assert order.customer_id == customer_id
    assert order.total_amount == Decimal("42.50")

    assert published["event_type"] == "order.created"
    assert published["payload"]["order_id"] == str(order.id)
    assert published["payload"]["total_amount"] == "42.50"


async def test_create_order_from_workflow_defaults_payment_method_to_none(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_publish_trigger_event(session, *, tenant_id, event_type, payload):
        return None

    monkeypatch.setattr(orders_service.event_bus, "publish_trigger_event", fake_publish_trigger_event)

    session = _FakeSession()
    payload = OrderCreate(customer_id=uuid.uuid4(), total_amount=Decimal("1"), currency="USD", line_items=[])

    order = await orders_service.create_order_from_workflow(
        session, uuid.uuid4(), payload, workflow_run_id=uuid.uuid4()
    )

    assert order.payment_method is None


async def test_create_order_is_unaffected_by_the_new_workflow_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression check: `create_order` (real checkout) never sets
    `source`/`created_by_workflow_run_id`/`payment_method` explicitly - it
    still relies purely on the columns' DB-side defaults (checked directly
    against the model in test_orders_model, not reproducible with a fake
    session since those are server_default/default values applied at real
    flush time, not by the Python constructor)."""
    published: dict[str, Any] = {}

    async def fake_publish_trigger_event(session, *, tenant_id, event_type, payload):
        published["called"] = True

    monkeypatch.setattr(orders_service.event_bus, "publish_trigger_event", fake_publish_trigger_event)

    session = _FakeSession()
    payload = OrderCreate(customer_id=uuid.uuid4(), total_amount=Decimal("5"), currency="USD", line_items=[])

    order = await orders_service.create_order(session, uuid.uuid4(), payload)

    assert published["called"] is True
    # Unset on the Python side (create_order never passes these kwargs) -
    # they only become "checkout"/NULL for real once a real flush applies
    # the column's `default`/`server_default`.
    assert order.source is None
    assert order.created_by_workflow_run_id is None
    assert order.payment_method is None


async def test_module_create_on_orders_still_fails_cleanly() -> None:
    """The core safeguard this whole part exists to preserve: adding the
    new `orders.create_from_conversation` node must NOT give the generic
    `module.create` executor a way to create orders. `OrdersQueryAdapter`
    (Phase 6) still has no `create` override, so it falls back to the base
    `ModuleQueryAdapter.create`'s `NotImplementedError`, and `module.create`
    turns that into a clean `Failure`, not an exception or a created row."""
    adapter = module_query_registry.get_or_none("orders")
    assert adapter is not None
    with pytest.raises(NotImplementedError):
        await adapter.create(None, tenant_id=uuid.uuid4(), fields={"customer_id": str(uuid.uuid4())})

    executor = module_create_node.ModuleCreateExecutor()
    context = ExecutionContext(
        session=None,
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="node-under-test",
        config={"module": "orders", "fields": {"customer_id": str(uuid.uuid4())}},
        variables={},
    )

    result = await executor.execute(context)

    assert isinstance(result, Failure)
    assert "does not support create" in result.error
