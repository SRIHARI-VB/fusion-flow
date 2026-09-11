"""`orders.create_from_cart` — creates a real order from an arbitrary-size
WhatsApp Commerce Catalog cart (`whatsapp.ask_for_cart`'s submitted
reply), via `orders_service.create_order_from_workflow`.

A **separate** node from `orders.create_from_conversation` rather than an
extension of it - that node is already tested and used by other
templates/workflows for its own hand-composed, small, fixed-at-authoring-
time line-item list; this one's whole reason to exist is the opposite
shape (an arbitrary-length list only known at run time), so keeping them
apart matches this codebase's established "don't touch already-tested
code for no functional gain" convention rather than bolting a second mode
onto the existing node's config.

`cart_items_path` is a plain dot-path (like `condition.field_compare`'s
`field_path`/`condition.multi_branch`'s case `field_path`s), NOT a
`{{...}}`-wrapped template - it names *where* in the run's variable
context to find the cart's item list, e.g.
`"ask_for_cart.reply.product_items"`; the raw list itself (not a
stringified copy of it) is what gets iterated below.

Each cart item's `product_retailer_id` is looked up against this
tenant's own `ProductService` catalog - re-deriving `name`/`base_price`
from our own source of truth rather than trusting whatever `item_price`
the customer's WhatsApp client happened to send (that price reflects what
they saw when they last opened the catalog inside WhatsApp, which can
drift from what a product actually costs right now).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.catalog import service as catalog_service
from fusionflow.modules.orders import service as orders_service
from fusionflow.modules.orders.schemas import OrderCreate
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate, resolve_path

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "order_id": {"type": "string"},
        "total_amount": {"type": "string"},
        "payment_method": {"type": "string"},
        "item_count": {"type": "integer"},
    },
}


class CreateOrderFromCartConfig(BaseModel):
    customer_id: str = Field(min_length=1, description="Customer id (UUID), may reference the run context.")
    cart_items_path: str = Field(
        min_length=1,
        description=(
            "Plain dot-path (no {{...}}) to the cart's product_items list in the run context, "
            "e.g. 'ask_for_cart.reply.product_items'."
        ),
    )
    currency: str = Field(default="USD", min_length=3, max_length=3)
    payment_method: str = Field(pattern="^(cod|prepaid)$")


class CreateOrderFromCartExecutor(NodeExecutor):
    node_type = "orders.create_from_cart"
    kind = "action"
    category = "Ecommerce"
    palette_group = "Records"
    icon = "shopping-cart"
    label = "Create Order (from Cart)"
    description = (
        "Creates a real order from a WhatsApp Commerce Catalog cart, re-pricing every item against "
        "your current product catalog."
    )
    config_model = CreateOrderFromCartConfig
    required_connector_type_key = "orders"
    output_schema = _OUTPUT_SCHEMA
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = CreateOrderFromCartConfig.model_validate(context.config)

        resolved_customer_id = interpolate(config.customer_id, context.variables)
        try:
            customer_id = uuid.UUID(resolved_customer_id)
        except ValueError:
            return Failure(f"customer_id {resolved_customer_id!r} is not a valid UUID")

        cart_items = resolve_path(context.variables, config.cart_items_path)
        if not isinstance(cart_items, list) or not cart_items:
            return Failure(f"cart is empty or not found at {config.cart_items_path!r}")

        line_items: list[dict[str, Any]] = []
        total_amount = Decimal("0")
        for raw_item in cart_items:
            retailer_id = raw_item.get("product_retailer_id") if isinstance(raw_item, dict) else None
            try:
                product_id = uuid.UUID(str(retailer_id))
            except (ValueError, TypeError):
                return Failure(f"cart item has an invalid product_retailer_id: {retailer_id!r}")

            product = await catalog_service.get_product_service(
                context.session, tenant_id=context.tenant_id, item_id=product_id
            )
            if product is None:
                return Failure(f"cart references unknown product {product_id}")

            quantity = int(raw_item.get("quantity", 1))
            total_amount += product.base_price * quantity
            line_items.append(
                {
                    "product_id": str(product.id),
                    "name": product.name,
                    "quantity": quantity,
                    "price": str(product.base_price),
                }
            )

        order = await orders_service.create_order_from_workflow(
            context.session,
            context.tenant_id,
            OrderCreate(
                customer_id=customer_id,
                total_amount=total_amount,
                currency=config.currency,
                line_items=line_items,
            ),
            workflow_run_id=context.run_id,
            payment_method=config.payment_method,
        )

        return Success(
            output={
                "order_id": str(order.id),
                "total_amount": str(order.total_amount),
                "payment_method": config.payment_method,
                "item_count": len(line_items),
            }
        )


node_executor_registry.register(CreateOrderFromCartExecutor())
