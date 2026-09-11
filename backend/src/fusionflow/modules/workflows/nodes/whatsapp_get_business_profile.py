"""`whatsapp.get_business_profile` — reads the connected WABA phone number's
business profile
(`modules/connectors/whatsapp/adapter.py::WhatsAppAdapter.get_business_profile`).
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
from fusionflow.modules.workflows.nodes._whatsapp_common import resolve_whatsapp_instance


class GetBusinessProfileConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)


class GetBusinessProfileExecutor(NodeExecutor):
    node_type = "whatsapp.get_business_profile"
    kind = "action"
    category = "Messages"
    subcategory = "Business Profile"
    label = "Get WhatsApp Business Profile"
    description = "Reads the connected WhatsApp number's business profile (about, address, description, ...)."
    config_model = GetBusinessProfileConfig
    required_connector_type_key = "whatsapp"

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = GetBusinessProfileConfig.model_validate(context.config)

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        profile = await whatsapp_adapter.get_business_profile(instance=instance, session=context.session)
        return Success(output={"profile": profile})


node_executor_registry.register(GetBusinessProfileExecutor())
