"""`whatsapp.send_location` — sends an outbound session location message
through a connected WhatsApp connector instance
(`modules/connectors/whatsapp/adapter.py::WhatsAppAdapter.send_location_message`).
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


class SendLocationConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(min_length=1, description="Recipient wa_id. May reference the run context.")
    latitude: float
    longitude: float
    name: str | None = Field(default=None, description="Optional location name, e.g. a store name.")
    address: str | None = None


class SendLocationExecutor(NodeExecutor):
    node_type = "whatsapp.send_location"
    kind = "action"
    category = "Messages"
    subcategory = "Location"
    label = "Send WhatsApp Location"
    description = "Sends an outbound location message through a connected WhatsApp connector instance."
    config_model = SendLocationConfig
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = SendLocationConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)
        name = interpolate(config.name, context.variables) if config.name else None
        address = interpolate(config.address, context.variables) if config.address else None

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        await whatsapp_adapter.send_location_message(
            instance=instance,
            to=to,
            latitude=config.latitude,
            longitude=config.longitude,
            name=name,
            address=address,
            session=context.session,
        )
        return Success(output={"to": to, "latitude": config.latitude, "longitude": config.longitude})


node_executor_registry.register(SendLocationExecutor())
