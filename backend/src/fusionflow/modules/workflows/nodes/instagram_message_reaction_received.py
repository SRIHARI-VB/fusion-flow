"""`instagram.message_reaction_received` — fires when someone reacts to (or
un-reacts to) a message in a conversation with a connected Instagram
account. Delivered as `messaging[].reaction` on the Messaging webhook
(`modules/connectors/instagram/adapter.py::_extract_message_reaction`).

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

NODE_TYPE = "instagram.message_reaction_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "message_id": {"type": "string"},
        "action": {"type": "string"},
        "reaction": {"type": "string"},
    },
}


class InstagramMessageReactionReceivedConfig(BaseModel):
    """No required fields — which connector instance fired is implicit in
    which `workflow_triggers` row matched the inbox event, not baked into
    the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class InstagramMessageReactionReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "Instagram Message Reaction Received"
    description = (
        "Fires when someone reacts to (or removes a reaction from) a message in a conversation "
        "with a connected Instagram account. Run context is seeded with the reactor's "
        "Instagram-scoped id ('from'), the reacted-to message id, whether this is a react or "
        "unreact ('action'), and the reaction type (e.g. 'love')."
    )
    config_model = InstagramMessageReactionReceivedConfig
    required_connector_type_key = "instagram"
    output_schema = _OUTPUT_SCHEMA
    applicable_purposes = ["automation"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = InstagramMessageReactionReceivedExecutor()
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
