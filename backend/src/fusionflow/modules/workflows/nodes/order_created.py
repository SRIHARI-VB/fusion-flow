"""`order.created` — fires when `modules/orders/service.py::create_order`
calls `event_bus.publish_trigger_event` right after inserting the new
`Order` row.

Registered in both registries, same "pass through the triggering payload"
shape as `manual_test_trigger.py` / `whatsapp_message_received.py`.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    TriggerDefinition,
    node_executor_registry,
    trigger_registry,
)

NODE_TYPE = "order.created"


class OrderCreatedConfig(BaseModel):
    """No required fields — this trigger fires for any order created in the
    tenant, not scoped to a particular customer/product at the node level."""

    description: str | None = Field(default=None, max_length=200)


class OrderCreatedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Ecommerce"
    label = "Order Created"
    description = (
        "Fires when a new order is created for this business. Run context is "
        "seeded with order_id, customer_id, total_amount, currency, and status."
    )
    config_model = OrderCreatedConfig

    async def execute(self, context: ExecutionContext) -> NodeResult:
        # `variables["trigger"]` was seeded by run_loop.execute_run from the
        # payload `publish_trigger_event` wrote (see orders/service.py).
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = OrderCreatedExecutor()
node_executor_registry.register(_executor)
trigger_registry.register(
    TriggerDefinition(
        trigger_type=_executor.node_type,
        category=_executor.category,
        label=_executor.label,
        description=_executor.description,
        config_model=_executor.config_model,
    )
)
