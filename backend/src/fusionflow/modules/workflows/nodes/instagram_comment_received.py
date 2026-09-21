"""`instagram.comment_received` — fires when the Instagram adapter's
`handle_webhook` detects an inbound comment on a connected post/reel and
calls `event_bus.publish_trigger_event`
(`modules/connectors/instagram/adapter.py::handle_webhook`).

This is the trigger the `instagram.comment_automation` predefined
automation (see `modules/predefined_automations/`) builds its generated
graph around — a `condition.field_compare` node checking `trigger.text`
against the wizard's configured keyword sits between this trigger and the
`connector.action` node that calls `reply_to_comment`/`send_direct_message`.

Same thin-echo-trigger shape as `whatsapp_message_received.py`.
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

NODE_TYPE = "instagram.comment_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "comment_id": {"type": "string"},
        "text": {"type": "string"},
        "from_id": {"type": "string"},
        "from_username": {"type": "string"},
        "media_id": {"type": "string"},
    },
}


class InstagramCommentReceivedConfig(BaseModel):
    """No required fields — which connector instance fired is implicit in
    which `workflow_triggers` row matched the inbox event, not baked into
    the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class InstagramCommentReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "Instagram Comment Received"
    description = (
        "Fires when a post or reel on a connected Instagram account receives an inbound "
        "comment. Run context is seeded with the comment id, text, commenter's Instagram-"
        "scoped id and username, and the media id it was left on."
    )
    config_model = InstagramCommentReceivedConfig
    required_connector_type_key = "instagram"
    output_schema = _OUTPUT_SCHEMA
    applicable_purposes = ["automation"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = InstagramCommentReceivedExecutor()
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
