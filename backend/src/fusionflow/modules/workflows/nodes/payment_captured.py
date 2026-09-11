"""`payment.captured` — fires when `RazorpayAdapter.handle_webhook` upserts a
`Payment` row whose mapped status is `PaymentStatus.SUCCEEDED` and calls
`event_bus.publish_trigger_event` (see `modules/connectors/razorpay/adapter.py`).

Registered in both registries, same "pass through the triggering payload"
shape as `order_created.py` / `whatsapp_message_received.py`.
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

NODE_TYPE = "payment.captured"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "payment_id": {"type": "string"},
        "order_id": {"type": "string"},
        "customer_id": {"type": "string"},
        "amount": {"type": "string"},
        "currency": {"type": "string"},
        "status": {"type": "string"},
    },
}


class PaymentCapturedConfig(BaseModel):
    """No required fields — this trigger fires for any captured payment in
    the tenant, not scoped to a particular order/customer at the node level."""

    description: str | None = Field(default=None, max_length=200)


class PaymentCapturedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Ecommerce"
    label = "Payment Captured"
    description = (
        "Fires when a payment is successfully captured for this business. Run context is "
        "seeded with payment_id, order_id, customer_id, amount, currency, and status."
    )
    config_model = PaymentCapturedConfig
    required_connector_type_key = "payments"
    output_schema = _OUTPUT_SCHEMA

    async def execute(self, context: ExecutionContext) -> NodeResult:
        # `variables["trigger"]` was seeded by run_loop.execute_run from the
        # payload `publish_trigger_event` wrote (see razorpay/adapter.py).
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = PaymentCapturedExecutor()
node_executor_registry.register(_executor)
trigger_registry.register(
    TriggerDefinition(
        trigger_type=_executor.node_type,
        category=_executor.category,
        label=_executor.label,
        description=_executor.description,
        config_model=_executor.config_model,
        required_connector_type_key=_executor.required_connector_type_key,
        output_schema=_executor.output_schema,
    )
)
