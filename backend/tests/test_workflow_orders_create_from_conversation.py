"""Offline unit tests for `orders.create_from_conversation` (Phase 8 Part
C) - the new, dedicated, narrower order-creation node used by a
conversational WhatsApp ordering flow, deliberately separate from the
generic `module.create` executor.

Same "no Postgres required" philosophy as `test_workflow_connector_nodes.py`:
`orders_service.create_order_from_workflow` is monkeypatched rather than
exercised against a real session.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from fusionflow.modules.orders.models import Order, OrderStatus
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.nodes import orders_create_from_conversation as node_module

pytestmark = pytest.mark.asyncio


def _context(config: dict[str, Any], variables: dict[str, Any] | None = None) -> ExecutionContext:
    return ExecutionContext(
        session=None,
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="node-under-test",
        config=config,
        variables=variables or {},
    )


_VALID_CONFIG = {
    "customer_id": "{{trigger.customer_id}}",
    "line_items": [{"product_id": "p1", "name": "Blue T-Shirt", "quantity": 2, "price": "{{trigger.price}}"}],
    "currency": "USD",
    "payment_method": "cod",
}


async def test_config_rejects_empty_line_items() -> None:
    executor = node_module.CreateOrderFromConversationExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config(
            {"customer_id": "abc", "line_items": [], "payment_method": "cod"}
        )


async def test_config_rejects_bad_payment_method() -> None:
    executor = node_module.CreateOrderFromConversationExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config(
            {
                "customer_id": "abc",
                "line_items": [{"name": "x", "price": "1.00"}],
                "payment_method": "bitcoin",
            }
        )


async def test_execute_invalid_customer_id_is_a_clean_failure() -> None:
    executor = node_module.CreateOrderFromConversationExecutor()
    context = _context(
        {**_VALID_CONFIG, "customer_id": "not-a-uuid"},
        {"trigger": {"customer_id": "not-a-uuid", "price": "10.00"}},
    )

    result = await executor.execute(context)

    assert isinstance(result, Failure)
    assert "not a valid UUID" in result.error


async def test_execute_invalid_price_is_a_clean_failure() -> None:
    executor = node_module.CreateOrderFromConversationExecutor()
    customer_id = uuid.uuid4()
    context = _context(
        _VALID_CONFIG,
        {"trigger": {"customer_id": str(customer_id), "price": "not-a-number"}},
    )

    result = await executor.execute(context)

    assert isinstance(result, Failure)
    assert "not a valid decimal" in result.error


async def test_execute_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = node_module.CreateOrderFromConversationExecutor()
    tenant_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    run_id = uuid.uuid4()

    created_order = Order(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        customer_id=customer_id,
        status=OrderStatus.PENDING,
        total_amount=Decimal("20.00"),
        currency="USD",
        line_items=[],
        source="workflow",
        created_by_workflow_run_id=run_id,
        payment_method="cod",
    )

    captured: dict[str, Any] = {}

    async def fake_create_order_from_workflow(session, tid, payload, *, workflow_run_id, payment_method=None):
        captured["tenant_id"] = tid
        captured["payload"] = payload
        captured["workflow_run_id"] = workflow_run_id
        captured["payment_method"] = payment_method
        return created_order

    monkeypatch.setattr(node_module.orders_service, "create_order_from_workflow", fake_create_order_from_workflow)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=run_id,
        node_id="create_order",
        config=_VALID_CONFIG,
        variables={"trigger": {"customer_id": str(customer_id), "price": "10.00"}},
    )

    result = await executor.execute(context)

    assert isinstance(result, Success)
    assert result.output == {
        "order_id": str(created_order.id),
        "total_amount": "20.00",
        "payment_method": "cod",
    }
    assert captured["tenant_id"] == tenant_id
    assert captured["workflow_run_id"] == run_id
    assert captured["payment_method"] == "cod"
    payload = captured["payload"]
    assert payload.customer_id == customer_id
    assert payload.total_amount == Decimal("20.00")
    assert payload.line_items == [{"product_id": "p1", "name": "Blue T-Shirt", "quantity": 2, "price": "10.00"}]


async def test_execute_propagates_service_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors create_ticket.py's matching test - this node is also
    `retryable = True`, so an unhandled service exception should propagate
    (not be swallowed into a permanent Failure) so run_loop's retry
    machinery can act on it."""
    executor = node_module.CreateOrderFromConversationExecutor()
    assert executor.retryable is True
    assert executor.max_retries == 2

    async def fake_create_order_from_workflow(session, tid, payload, *, workflow_run_id, payment_method=None):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(node_module.orders_service, "create_order_from_workflow", fake_create_order_from_workflow)

    context = ExecutionContext(
        session=None,
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="create_order",
        config=_VALID_CONFIG,
        variables={"trigger": {"customer_id": str(uuid.uuid4()), "price": "10.00"}},
    )

    with pytest.raises(RuntimeError, match="db exploded"):
        await executor.execute(context)
