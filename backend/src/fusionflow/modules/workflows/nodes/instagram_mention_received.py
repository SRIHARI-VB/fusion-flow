"""`instagram.mention_received` — fires when someone `@mentions` a
connected Instagram account in a comment or caption on media THEY own
(not this account's own media - see `instagram_comment_received.py` for
that case). Delivered as a `mentions`-field webhook entry, resolved to
actual text/username via a follow-up lookup
(`modules/connectors/instagram/adapter.py::_extract_mention` +
`_resolve_mention_details`).

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

NODE_TYPE = "instagram.mention_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "media_id": {"type": "string"},
        "comment_id": {"type": "string"},
        "text": {"type": "string"},
        "from_id": {"type": "string"},
        "from_username": {"type": "string"},
    },
}


class InstagramMentionReceivedConfig(BaseModel):
    """No required fields — which connector instance fired is implicit in
    which `workflow_triggers` row matched the inbox event, not baked into
    the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class InstagramMentionReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "Instagram Mention Received"
    description = (
        "Fires when someone @mentions a connected Instagram account in a comment or caption on "
        "media they own. Run context is seeded with the media/comment ids, the resolved mention "
        "text, and the mentioner's id/username (text and mentioner may be empty if Meta's "
        "detail lookup couldn't be completed - a keyword condition simply won't match then)."
    )
    config_model = InstagramMentionReceivedConfig
    required_connector_type_key = "instagram"
    output_schema = _OUTPUT_SCHEMA
    applicable_purposes = ["automation"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = InstagramMentionReceivedExecutor()
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
