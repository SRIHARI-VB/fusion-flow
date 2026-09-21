"""`facebook.message_received` — fires when the Facebook adapter's
`handle_webhook` detects an inbound Messenger message and calls
`event_bus.publish_trigger_event`
(`modules/connectors/facebook/adapter.py::handle_webhook`).

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

NODE_TYPE = "facebook.message_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "message_id": {"type": "string"},
        "text": {"type": "string"},
    },
}


class FacebookMessageReceivedConfig(BaseModel):
    """No required fields — which connector instance fired is implicit in
    which `workflow_triggers` row matched the inbox event, not baked into
    the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class FacebookMessageReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "Facebook Message Received"
    description = (
        "Fires when a Facebook Page connected to this business receives an inbound "
        "Messenger message. Run context is seeded with the sender's PSID ('from'), "
        "message id, and text."
    )
    config_model = FacebookMessageReceivedConfig
    required_connector_type_key = "facebook"
    output_schema = _OUTPUT_SCHEMA
    applicable_purposes = ["automation"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = FacebookMessageReceivedExecutor()
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
