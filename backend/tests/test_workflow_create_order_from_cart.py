"""Offline unit tests for `orders.create_from_cart` (WhatsApp Commerce
Catalog cart support) - `orders.create_from_conversation`'s sibling for an
arbitrary-size cart.

Same "no Postgres required" philosophy as
`test_workflow_orders_create_from_conversation.py`:
`orders_service.create_order_from_workflow` and
`catalog_service.get_product_service` are both monkeypatched, the latter
returning real `ProductService` ORM instances (constructed directly, not
persisted) so `.base_price`/`.name` attribute access is exercised for
real, not against a plain dict stand-in.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest

from fusionflow.modules.catalog.models import ProductService, ProductServiceType
from fusionflow.modules.orders.models import Order, OrderStatus
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.nodes import orders_create_from_cart as node_module

pytestmark = pytest.mark.asyncio


def _product(tenant_id: uuid.UUID, *, name: str, price: str) -> ProductService:
    return ProductService(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        entity_type=ProductServiceType.PRODUCT,
        name=name,
        base_price=Decimal(price),
        is_active=True,
        custom_fields={},
    )


def _context(config: dict[str, Any], variables: dict[str, Any], tenant_id: uuid.UUID) -> ExecutionContext:
    return ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="create_order",
        config=config,
        variables=variables,
    )


_BASE_CONFIG = {
    "customer_id": "{{trigger.customer_id}}",
    "cart_items_path": "ask_for_cart.reply.product_items",
    "currency": "INR",
    "payment_method": "cod",
}


async def test_execute_invalid_customer_id_is_a_clean_failure() -> None:
    executor = node_module.CreateOrderFromCartExecutor()
    context = _context(
        _BASE_CONFIG,
        {"trigger": {"customer_id": "not-a-uuid"}, "ask_for_cart": {"reply": {"product_items": []}}},
        uuid.uuid4(),
    )

    result = await executor.execute(context)

    assert isinstance(result, Failure)
    assert "not a valid UUID" in result.error


async def test_execute_missing_cart_is_a_clean_failure() -> None:
    executor = node_module.CreateOrderFromCartExecutor()
    context = _context(
        _BASE_CONFIG,
        {"trigger": {"customer_id": str(uuid.uuid4())}},
        uuid.uuid4(),
    )

    result = await executor.execute(context)

    assert isinstance(result, Failure)
    assert "cart is empty" in result.error


async def test_execute_empty_cart_is_a_clean_failure() -> None:
    executor = node_module.CreateOrderFromCartExecutor()
    context = _context(
        _BASE_CONFIG,
        {"trigger": {"customer_id": str(uuid.uuid4())}, "ask_for_cart": {"reply": {"product_items": []}}},
        uuid.uuid4(),
    )

    result = await executor.execute(context)

    assert isinstance(result, Failure)
    assert "cart is empty" in result.error


async def test_execute_unknown_product_is_a_clean_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = node_module.CreateOrderFromCartExecutor()
    tenant_id = uuid.uuid4()

    async def fake_get_product_service(session, *, tenant_id, item_id):
        return None

    monkeypatch.setattr(node_module.catalog_service, "get_product_service", fake_get_product_service)

    context = _context(
        _BASE_CONFIG,
        {
            "trigger": {"customer_id": str(uuid.uuid4())},
            "ask_for_cart": {"reply": {"product_items": [{"product_retailer_id": str(uuid.uuid4()), "quantity": "1"}]}},
        },
        tenant_id,
    )

    result = await executor.execute(context)

    assert isinstance(result, Failure)
    assert "unknown product" in result.error


async def test_execute_happy_path_sums_multiple_items(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = node_module.CreateOrderFromCartExecutor()
    tenant_id = uuid.uuid4()
    customer_id = uuid.uuid4()
    run_id = uuid.uuid4()

    pizza = _product(tenant_id, name="Pizza", price="9.99")
    burger = _product(tenant_id, name="Burger", price="5.50")
    products_by_id = {pizza.id: pizza, burger.id: burger}

    async def fake_get_product_service(session, *, tenant_id, item_id):
        return products_by_id.get(item_id)

    created_order = Order(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        customer_id=customer_id,
        status=OrderStatus.PENDING,
        total_amount=Decimal("21.48"),
        currency="INR",
        line_items=[],
        source="workflow",
        created_by_workflow_run_id=run_id,
        payment_method="cod",
    )

    captured: dict[str, Any] = {}

    async def fake_create_order_from_workflow(session, tid, payload, *, workflow_run_id, payment_method=None):
        captured["payload"] = payload
        return created_order

    monkeypatch.setattr(node_module.catalog_service, "get_product_service", fake_get_product_service)
    monkeypatch.setattr(node_module.orders_service, "create_order_from_workflow", fake_create_order_from_workflow)

    context = _context(
        _BASE_CONFIG,
        {
            "trigger": {"customer_id": str(customer_id)},
            "ask_for_cart": {
                "reply": {
                    "product_items": [
                        {"product_retailer_id": str(pizza.id), "quantity": "2", "item_price": "999.00"},
                        {"product_retailer_id": str(burger.id), "quantity": "1"},
                    ]
                }
            },
        },
        tenant_id,
    )

    result = await executor.execute(context)

    assert isinstance(result, Success)
    assert result.output["item_count"] == 2
    assert result.output["order_id"] == str(created_order.id)
    # Re-priced from our own catalog (9.99*2 + 5.50*1 = 25.48), NOT from the
    # cart's own stale `item_price` ("999.00") - the whole point of this
    # node re-deriving prices rather than trusting the webhook.
    assert captured["payload"].total_amount == Decimal("25.48")
    assert captured["payload"].line_items == [
        {"product_id": str(pizza.id), "name": "Pizza", "quantity": 2, "price": "9.99"},
        {"product_id": str(burger.id), "name": "Burger", "quantity": 1, "price": "5.50"},
    ]
