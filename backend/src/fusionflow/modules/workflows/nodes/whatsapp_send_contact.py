"""`whatsapp.send_contact` — sends an outbound session contact-card
message through a connected WhatsApp connector instance
(`modules/connectors/whatsapp/adapter.py::WhatsAppAdapter.send_contact_message`).

`contacts` is a repeatable field (array of `{name, phone}`) - this is the
first node type whose config genuinely needs the array-of-objects form
support added in Part D (`jsonSchemaForm.ts`'s `array_object` field kind);
until that ships, the field is still fully valid/executable, just only
editable as raw JSON in the builder.
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


class ContactEntry(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)


class SendContactConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(min_length=1, description="Recipient wa_id. May reference the run context.")
    contacts: list[ContactEntry] = Field(min_length=1)


class SendContactExecutor(NodeExecutor):
    node_type = "whatsapp.send_contact"
    kind = "action"
    category = "Messages"
    subcategory = "Contact"
    label = "Send WhatsApp Contact"
    description = "Sends an outbound contact card through a connected WhatsApp connector instance."
    config_model = SendContactConfig
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = SendContactConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        await whatsapp_adapter.send_contact_message(
            instance=instance,
            to=to,
            contacts=[{"name": c.name, "phone": c.phone} for c in config.contacts],
            session=context.session,
        )
        return Success(output={"to": to, "contact_count": len(config.contacts)})


node_executor_registry.register(SendContactExecutor())
