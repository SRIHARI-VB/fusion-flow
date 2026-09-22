"""`instagram.story_reply_received` — fires when someone replies to a
Story posted by a connected Instagram account. Delivered through the same
Messaging webhook as a normal DM, distinguished by `message.reply_to.story`
being set (`modules/connectors/instagram/adapter.py::_extract_story_reply`).

Same thin-echo-trigger shape as `instagram_message_received.py`.
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

NODE_TYPE = "instagram.story_reply_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "message_id": {"type": "string"},
        "text": {"type": "string"},
        "story_id": {"type": "string"},
    },
}


class InstagramStoryReplyReceivedConfig(BaseModel):
    """No required fields — which connector instance fired is implicit in
    which `workflow_triggers` row matched the inbox event, not baked into
    the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class InstagramStoryReplyReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "Instagram Story Reply Received"
    description = (
        "Fires when someone replies to a Story posted by a connected Instagram account. Run "
        "context is seeded with the replier's Instagram-scoped id ('from'), message id, reply "
        "text, and the story id it was left on."
    )
    config_model = InstagramStoryReplyReceivedConfig
    required_connector_type_key = "instagram"
    output_schema = _OUTPUT_SCHEMA
    applicable_purposes = ["automation"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = InstagramStoryReplyReceivedExecutor()
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
        applicable_purposes=_executor.applicable_purposes,
    )
)
