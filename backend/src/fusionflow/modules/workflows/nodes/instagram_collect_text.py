"""`instagram.collect_text` — send an Instagram DM question, then pause the
run (Phase 8 Part A pause/resume) until this same contact's next reply
arrives on the same connector instance. Instagram's first multi-turn
building block, mirroring `whatsapp.collect_text`/`whatsapp.ask_question`'s
exact suspend/resume shape - the one piece `instagram/adapter.py::
handle_webhook` didn't have a resume-checking path for until this was
added (see that method's `find_pending_wait`/`publish_resume_event` call,
now wired in alongside this node).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.instagram.adapter import adapter as instagram_adapter
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Suspend,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate


class InstagramCollectTextConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    recipient_id: str = Field(
        min_length=1,
        description="The Instagram-scoped id to send the question to (usually {{trigger.from}}).",
        json_schema_extra={"format": "recipient"},
    )
    question: str = Field(
        min_length=1,
        description="The question's body text, e.g. 'What issue are you facing?'",
        json_schema_extra={"format": "textarea"},
    )


_OUTPUT_SCHEMA = {"type": "object", "properties": {"reply": {"type": "string"}}}


class InstagramCollectTextExecutor(NodeExecutor):
    node_type = "instagram.collect_text"
    kind = "action"
    category = "Messages"
    subcategory = "Ask"
    palette_group = "Talk to Customer"
    icon = "message-square-text"
    label = "Ask for a Text Reply"
    description = "Sends a question via Instagram DM, then pauses the run until this contact's next reply arrives."
    config_model = InstagramCollectTextConfig
    output_schema = _OUTPUT_SCHEMA
    can_suspend = True
    # See whatsapp_ask_question.py's identical comment - pausing for one
    # reply can't work inside a broadcast's flow.loop fan-out.
    applicable_purposes = ["automation"]
    required_connector_type_key = "instagram"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = InstagramCollectTextConfig.model_validate(context.config)
        recipient_id = interpolate(config.recipient_id, context.variables)
        question = interpolate(config.question, context.variables)

        try:
            connector_instance_id = uuid.UUID(config.connector_instance_id)
        except ValueError:
            return Failure(f"connector_instance_id {config.connector_instance_id!r} is not a valid UUID")

        instance = await connector_service.get_instance(
            context.session, tenant_id=context.tenant_id, instance_id=connector_instance_id
        )
        if instance is None:
            return Failure(f"connector instance {connector_instance_id} not found for this tenant")

        await instagram_adapter.send_direct_message(
            instance=instance, session=context.session, recipient_id=recipient_id, text=question
        )
        return Suspend(correlation_key=recipient_id)

    async def extract_resume_value(self, config: dict[str, Any], resume_payload: dict[str, Any]) -> Any:
        # `run_loop.py::resume_run` wraps whatever this returns as
        # `variables[node_id] = {"reply": answer}` itself - returning the
        # raw text directly here is what makes `{{this_node.reply}}` a
        # plain string downstream, matching `output_schema` above.
        return resume_payload.get("text")


node_executor_registry.register(InstagramCollectTextExecutor())
