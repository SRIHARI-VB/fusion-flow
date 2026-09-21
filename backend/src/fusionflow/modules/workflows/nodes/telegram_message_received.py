"""`telegram.message_received` — fires when the Telegram adapter's
`handle_webhook` detects an inbound message and calls
`event_bus.publish_trigger_event`
(`modules/connectors/telegram/adapter.py::handle_webhook`).

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

NODE_TYPE = "telegram.message_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "chat_id": {"type": "integer"},
        "message_id": {"type": "integer"},
        "text": {"type": "string"},
        "from_username": {"type": "string"},
    },
}


class TelegramMessageReceivedConfig(BaseModel):
    """No required fields — which connector instance fired is implicit in
    which `workflow_triggers` row matched the inbox event, not baked into
    the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class TelegramMessageReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "Telegram Message Received"
    description = (
        "Fires when a Telegram bot connected to this business receives an inbound message. "
        "Run context is seeded with the chat id, message id, text, and sender's username."
    )
    config_model = TelegramMessageReceivedConfig
    required_connector_type_key = "telegram"
    output_schema = _OUTPUT_SCHEMA
    applicable_purposes = ["automation"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = TelegramMessageReceivedExecutor()
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
