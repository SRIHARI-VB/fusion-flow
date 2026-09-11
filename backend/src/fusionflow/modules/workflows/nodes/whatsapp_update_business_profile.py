"""`whatsapp.update_business_profile` — updates the connected WABA phone
number's business profile
(`modules/connectors/whatsapp/adapter.py::WhatsAppAdapter.update_business_profile`).
"""

from __future__ import annotations

from typing import Any

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


class UpdateBusinessProfileConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    profile_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Any of about/address/description/email/websites/vertical.",
    )


class UpdateBusinessProfileExecutor(NodeExecutor):
    node_type = "whatsapp.update_business_profile"
    kind = "action"
    category = "Messages"
    subcategory = "Business Profile"
    label = "Update WhatsApp Business Profile"
    description = "Updates the connected WhatsApp number's business profile."
    config_model = UpdateBusinessProfileConfig
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = UpdateBusinessProfileConfig.model_validate(context.config)

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        updated = await whatsapp_adapter.update_business_profile(
            instance=instance, profile_fields=config.profile_fields, session=context.session
        )
        return Success(output={"profile": updated})


node_executor_registry.register(UpdateBusinessProfileExecutor())
