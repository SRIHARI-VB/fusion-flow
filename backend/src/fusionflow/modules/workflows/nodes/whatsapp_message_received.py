"""`whatsapp.message_received` — fires when the WhatsApp adapter's
`handle_webhook` detects an inbound user message (as opposed to a status
callback) and calls `event_bus.publish_trigger_event`
(`modules/connectors/whatsapp/adapter.py::handle_webhook`).

Registered in both registries, same shape as `manual.test_trigger`: the
trigger's "execution" is simply seeding/echoing the run's variable context
from the payload the outbox poller (or simulate) seeded it with — see
`manual_test_trigger.py` for the identical pattern.
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

NODE_TYPE = "whatsapp.message_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "message_id": {"type": "string"},
        "type": {"type": "string"},
        "text": {"type": "object", "properties": {"body": {"type": "string"}}},
    },
}


class WhatsAppMessageReceivedConfig(BaseModel):
    """No required fields — which connector instance fired is implicit in
    which `workflow_triggers` row matched the inbox event, not baked into
    the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class WhatsAppMessageReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "WhatsApp Message Received"
    description = (
        "Fires when a WhatsApp number connected to this business receives an "
        "inbound user message. Run context is seeded with the sender's number "
        "('from'), message id, type, and text body."
    )
    config_model = WhatsAppMessageReceivedConfig
    required_connector_type_key = "whatsapp"
    output_schema = _OUTPUT_SCHEMA

    async def execute(self, context: ExecutionContext) -> NodeResult:
        # `variables["trigger"]` was seeded by run_loop.execute_run from the
        # payload `publish_trigger_event` wrote (see whatsapp/adapter.py).
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = WhatsAppMessageReceivedExecutor()
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
    )
)
