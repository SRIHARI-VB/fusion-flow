"""`whatsapp.send_media` — sends an outbound session (free-form) media
message (image/video/audio/document) through a connected WhatsApp
connector instance
(`modules/connectors/whatsapp/adapter.py::WhatsAppAdapter.send_media_message`).

Session message: only deliverable within the 24-hour customer service
window (Meta rejects it outside that window - surfaced as a clean node
failure via the adapter's real HTTP error, not silently dropped). For a
marketing/utility message outside that window, use
`whatsapp.send_template` instead.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

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


class SendMediaConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(min_length=1, description="Recipient wa_id. May reference the run context.")
    media_type: Literal["image", "video", "audio", "document"]
    media_url: str | None = Field(default=None, description="Publicly reachable URL - required unless media_id is set.")
    media_id: str | None = Field(default=None, description="A media id already uploaded to WhatsApp - alternative to media_url.")
    caption: str | None = Field(
        default=None, description="Not supported for audio.", json_schema_extra={"format": "textarea"}
    )
    filename: str | None = Field(default=None, description="Document filename shown to the recipient.")

    @model_validator(mode="after")
    def _require_url_or_id(self) -> "SendMediaConfig":
        if not self.media_url and not self.media_id:
            raise ValueError("either media_url or media_id is required")
        return self


class SendMediaExecutor(NodeExecutor):
    node_type = "whatsapp.send_media"
    kind = "action"
    category = "Messages"
    subcategory = "Media"
    label = "Send WhatsApp Media"
    description = "Sends an outbound image/video/audio/document message through a connected WhatsApp connector instance."
    config_model = SendMediaConfig
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = SendMediaConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)
        media_url = interpolate(config.media_url, context.variables) if config.media_url else None
        caption = interpolate(config.caption, context.variables) if config.caption else None

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        await whatsapp_adapter.send_media_message(
            instance=instance,
            to=to,
            media_type=config.media_type,
            media_url=media_url,
            media_id=config.media_id,
            caption=caption,
            filename=config.filename,
            session=context.session,
        )
        return Success(output={"to": to, "media_type": config.media_type})


node_executor_registry.register(SendMediaExecutor())
