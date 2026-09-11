"""`whatsapp.mark_as_read` — marks an inbound message as read (blue ticks)
through a connected WhatsApp connector instance
(`modules/connectors/whatsapp/adapter.py::WhatsAppAdapter.mark_message_as_read`).
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


class MarkAsReadConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    message_id: str = Field(
        min_length=1, description="Inbound message id, typically '{{trigger.message_id}}'."
    )


class MarkAsReadExecutor(NodeExecutor):
    node_type = "whatsapp.mark_as_read"
    kind = "action"
    category = "Messages"
    subcategory = "Status"
    label = "Mark WhatsApp Message as Read"
    description = "Marks an inbound WhatsApp message as read."
    config_model = MarkAsReadConfig
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = MarkAsReadConfig.model_validate(context.config)
        message_id = interpolate(config.message_id, context.variables)

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        await whatsapp_adapter.mark_message_as_read(instance=instance, message_id=message_id, session=context.session)
        return Success(output={"message_id": message_id})


node_executor_registry.register(MarkAsReadExecutor())
