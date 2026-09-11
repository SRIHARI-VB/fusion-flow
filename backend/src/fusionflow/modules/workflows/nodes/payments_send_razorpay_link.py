"""`payments.send_razorpay_link` — creates a real Razorpay payment link
(`RazorpayAdapter.create_payment_link`) and sends it to the customer over
WhatsApp, as one plain (non-suspending) action node.

There is deliberately no `payments.collect_payment` node that both asks
"COD or online?" AND does this - verified against `engine/run_loop.py`: a
`can_suspend` node's `execute()` call ends the instant it returns
`Suspend`; resuming later calls `extract_resume_value` on that same
node's *config*, not a second `execute()`, so one node can never
suspend-to-ask and then, still as itself, branch on the answer and make a
further provider call. The correct, and more composable, shape is: an
ordinary `whatsapp.ask_choice` node with two static options
(`{"id": "cod", "label": "Cash on Delivery"}` / `{"id": "online", "label":
"Pay Online"}`) - which already gets a `condition.multi_branch` compiled
in downstream, for free, by `engine/composite_branching.py` - with this
node wired to the "online" branch handle. An author can freely see,
rewire, or remove this step independently of the choice that led to it,
which is the actual point of this whole redesign: no hidden multi-step
behavior inside one opaque node.
"""

from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.razorpay.adapter import adapter as razorpay_adapter
from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate
from fusionflow.modules.workflows.nodes._whatsapp_common import resolve_whatsapp_instance

_LINK_PLACEHOLDER = "{{link}}"


class SendRazorpayLinkConfig(BaseModel):
    razorpay_connector_instance_id: str = Field(min_length=1)
    whatsapp_connector_instance_id: str = Field(min_length=1)
    to: str = Field(min_length=1, description="WhatsApp recipient wa_id for the payment-link message.")
    amount: str = Field(min_length=1, description="Templatable; parsed as a decimal, e.g. '{{order.total_amount}}'.")
    currency: str = Field(default="INR")
    order_id: str = Field(min_length=1, description="Templatable; parsed as a UUID, e.g. '{{create_order.order_id}}'.")
    customer_contact: str = Field(min_length=1, description="Templatable phone/email Razorpay requires.")
    message_template: str = Field(
        default=f"Please complete your payment: {_LINK_PLACEHOLDER}",
        description=f"Must contain the literal {_LINK_PLACEHOLDER} placeholder - substituted after the link "
        "is created, not through the normal {{...}} templating pass (the short_url doesn't exist yet "
        "when this node's other fields are interpolated).",
        json_schema_extra={"format": "textarea"},
    )


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"payment_link": {"type": "string"}, "provider_ref": {"type": "string"}},
}


class SendRazorpayLinkExecutor(NodeExecutor):
    node_type = "payments.send_razorpay_link"
    kind = "action"
    category = "Payments"
    palette_group = "Payments"
    icon = "credit-card"
    label = "Send Payment Link"
    description = "Creates a Razorpay payment link and sends it to the customer over WhatsApp."
    config_model = SendRazorpayLinkConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = SendRazorpayLinkConfig.model_validate(context.config)

        try:
            razorpay_instance_id = uuid.UUID(config.razorpay_connector_instance_id)
        except ValueError:
            return Failure(f"razorpay_connector_instance_id {config.razorpay_connector_instance_id!r} is not a valid UUID")
        razorpay_instance = await connector_service.get_instance(
            context.session, tenant_id=context.tenant_id, instance_id=razorpay_instance_id
        )
        if razorpay_instance is None:
            return Failure(f"connector instance {razorpay_instance_id} not found for this tenant")

        whatsapp_instance = await resolve_whatsapp_instance(context, config.whatsapp_connector_instance_id)
        if isinstance(whatsapp_instance, Failure):
            return whatsapp_instance

        amount_raw = interpolate(config.amount, context.variables)
        order_id_raw = interpolate(config.order_id, context.variables)
        customer_contact = interpolate(config.customer_contact, context.variables)
        to = interpolate(config.to, context.variables)

        try:
            amount = Decimal(amount_raw)
        except InvalidOperation:
            return Failure(f"amount {amount_raw!r} is not a valid decimal")
        try:
            order_id = uuid.UUID(order_id_raw)
        except ValueError:
            return Failure(f"order_id {order_id_raw!r} is not a valid UUID")

        try:
            result = await razorpay_adapter.create_payment_link(
                instance=razorpay_instance,
                amount=amount,
                currency=config.currency,
                order_id=order_id,
                customer_contact=customer_contact,
                session=context.session,
            )
        except ValueError as exc:
            return Failure(str(exc))

        payment_link = result.get("short_url", "")
        provider_ref = result.get("id", "")

        # Literal substitution only, deliberately NOT run through the
        # general `interpolate()` templating pass: `interpolate` replaces
        # any `{{path}}` it can't resolve with an empty string (see
        # `engine/templating.py`), and `link` is never a real variable-
        # context path - it would be silently wiped out before reaching
        # this replace if interpolated first.
        message = config.message_template.replace(_LINK_PLACEHOLDER, payment_link)
        await whatsapp_adapter.send_text_message(
            instance=whatsapp_instance, to=to, body=message, session=context.session
        )

        return Success(output={"payment_link": payment_link, "provider_ref": provider_ref})


node_executor_registry.register(SendRazorpayLinkExecutor())
