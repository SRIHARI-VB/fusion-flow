"""`whatsapp.send_interactive_buttons` — sends an outbound session message
with up to 3 quick-reply buttons through a connected WhatsApp connector
instance
(`modules/connectors/whatsapp/adapter.py::WhatsAppAdapter.send_interactive_message`).

A customer's tap fires `whatsapp.interactive_reply_received` with
`interactive.id` matching whichever button's `id` they tapped - wire a
`condition.multi_branch`/`condition.field_compare` node after that trigger
keyed on `interactive.id` to branch per button.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

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


class ButtonEntry(BaseModel):
    id: str = Field(min_length=1, description="Echoed back in interactive.id when the customer taps this button.")
    title: str = Field(min_length=1, max_length=20, description="Meta's own 20-character button label limit.")


class SendInteractiveButtonsConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(min_length=1, description="Recipient wa_id. May reference the run context.")
    body_text: str = Field(min_length=1, json_schema_extra={"format": "textarea"})
    buttons: list[ButtonEntry] = Field(min_length=1, max_length=3, description="Meta allows at most 3 quick-reply buttons.")


class SendInteractiveButtonsExecutor(NodeExecutor):
    node_type = "whatsapp.send_interactive_buttons"
    kind = "action"
    category = "Choices"
    subcategory = "Quick Reply"
    label = "Send WhatsApp Quick Reply Buttons"
    description = "Sends up to 3 quick-reply buttons; a tap fires whatsapp.interactive_reply_received."
    config_model = SendInteractiveButtonsConfig
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = SendInteractiveButtonsConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)
        body_text = interpolate(config.body_text, context.variables)

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        await whatsapp_adapter.send_interactive_message(
            instance=instance,
            to=to,
            body_text=body_text,
            interactive_type="button",
            buttons=[{"id": b.id, "title": b.title} for b in config.buttons],
            session=context.session,
        )
        return Success(output={"to": to, "button_count": len(config.buttons)})


node_executor_registry.register(SendInteractiveButtonsExecutor())
