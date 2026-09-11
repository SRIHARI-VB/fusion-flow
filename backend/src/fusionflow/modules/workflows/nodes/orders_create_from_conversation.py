"""`orders.create_from_conversation` — creates a real order from a
multi-turn WhatsApp conversation (Phase 8 Part C), via
`orders_service.create_order_from_workflow`.

This is deliberately a separate, narrower node from the generic
`module.create` executor, not a loosening of Phase 6's "no create for
orders" rule (see `modules/orders/workflow_adapter.py`'s docstring):
`OrdersQueryAdapter` still has no `create` method and must not gain one.
This node calls the orders service function directly, keeping the two
paths - generic module CRUD vs. this safeguarded conversational path -
architecturally distinct.

`customer_id` and each line item's string fields support the same
`{{dot.path}}` interpolation as every other templated node config in this
package - `_interpolate`/`_resolve_path` are `create_ticket.py`'s own
helpers, copied here rather than shared, per this project's established
"each node keeps its own private copy" convention (see
`engine/templating.py`'s docstring). Line items additionally go through
`module_registry.interpolate_dict_values` (one call per item) since each
is itself a dict of possibly-templated string values, not a single
string.
"""

from __future__ import annotations

import re
import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.orders import service as orders_service
from fusionflow.modules.orders.schemas import OrderCreate
from fusionflow.modules.workflows.engine.module_registry import interpolate_dict_values
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)

_TEMPLATE_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "order_id": {"type": "string"},
        "total_amount": {"type": "string"},
        "payment_method": {"type": "string"},
    },
}


def _resolve_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _interpolate(template: str, variables: dict[str, Any]) -> str:
    def _replace(match: "re.Match[str]") -> str:
        value = _resolve_path(variables, match.group(1))
        return "" if value is None else str(value)

    return _TEMPLATE_RE.sub(_replace, template)


class LineItem(BaseModel):
    product_id: str | None = None
    name: str = Field(min_length=1)
    quantity: int = Field(default=1, ge=1)
    # Kept as a templated string, like every other money-ish field in this
    # codebase's node configs, so `{{...}}` interpolation applies - parsed
    # to Decimal in `execute()` right before use.
    price: str = Field(min_length=1)


class CreateOrderFromConversationConfig(BaseModel):
    customer_id: str = Field(min_length=1, description="Customer id (UUID), may reference the run context.")
    line_items: list[LineItem] = Field(min_length=1)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    payment_method: str = Field(pattern="^(cod|prepaid)$")


class CreateOrderFromConversationExecutor(NodeExecutor):
    node_type = "orders.create_from_conversation"
    kind = "action"
    category = "Ecommerce"
    label = "Create Order (from Conversation)"
    description = (
        "Creates a real order from a conversational flow (e.g. WhatsApp guided ordering), "
        "once the customer has confirmed product/quantity/price and payment method."
    )
    config_model = CreateOrderFromConversationConfig
    required_connector_type_key = "orders"
    output_schema = _OUTPUT_SCHEMA
    # Mirrors create_ticket.py's reasoning: the retry target is a transient
    # DB hiccup on the insert, not a config problem - config/parse errors
    # below are returned as a clean Failure before the service call, so a
    # retry would never change their outcome.
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = CreateOrderFromConversationConfig.model_validate(context.config)

        resolved_customer_id = _interpolate(config.customer_id, context.variables)
        try:
            customer_id = uuid.UUID(resolved_customer_id)
        except ValueError:
            return Failure(f"customer_id {resolved_customer_id!r} is not a valid UUID")

        line_items: list[dict[str, Any]] = []
        total_amount = Decimal("0")
        for item in config.line_items:
            resolved = interpolate_dict_values(item.model_dump(), context.variables)
            try:
                price = Decimal(str(resolved["price"]))
            except (InvalidOperation, KeyError, TypeError):
                return Failure(f"line item price {resolved.get('price')!r} is not a valid decimal")
            quantity = int(resolved["quantity"])
            total_amount += price * quantity
            line_items.append(
                {
                    "product_id": resolved.get("product_id"),
                    "name": resolved["name"],
                    "quantity": quantity,
                    "price": str(price),
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
            }
        )


node_executor_registry.register(CreateOrderFromConversationExecutor())
