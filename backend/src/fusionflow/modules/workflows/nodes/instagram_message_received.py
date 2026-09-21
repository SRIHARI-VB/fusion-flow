"""`instagram.message_received` — fires when the Instagram adapter's
`handle_webhook` detects an inbound direct message and calls
`event_bus.publish_trigger_event`
(`modules/connectors/instagram/adapter.py::handle_webhook`).

Same thin-echo-trigger shape as `whatsapp_message_received.py` - the
trigger's "execution" is simply echoing the run's variable context from the
payload the outbox poller (or simulate) seeded it with.
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

NODE_TYPE = "instagram.message_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "message_id": {"type": "string"},
        "text": {"type": "string"},
    },
}


class InstagramMessageReceivedConfig(BaseModel):
    """No required fields — which connector instance fired is implicit in
    which `workflow_triggers` row matched the inbox event, not baked into
    the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class InstagramMessageReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "Instagram DM Received"
    description = (
        "Fires when an Instagram account connected to this business receives an inbound "
        "direct message. Run context is seeded with the sender's Instagram-scoped id "
        "('from'), message id, and text."
    )
    config_model = InstagramMessageReceivedConfig
    required_connector_type_key = "instagram"
    output_schema = _OUTPUT_SCHEMA
    applicable_purposes = ["automation"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = InstagramMessageReceivedExecutor()
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
