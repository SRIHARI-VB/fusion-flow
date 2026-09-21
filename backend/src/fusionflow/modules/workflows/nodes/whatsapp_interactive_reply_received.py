"""`whatsapp.interactive_reply_received` — fires when a customer taps a
quick-reply button or selects a list item sent by a prior
`whatsapp.send_interactive_buttons`/`whatsapp.send_interactive_list` node.

A dedicated trigger, separate from `whatsapp.message_received`, since
`WhatsAppAdapter.handle_webhook` routes an inbound message whose
`message_type == "interactive"` here exclusively (see that method's
routing comment) - a workflow built around "user clicked a button" gets
a clean trigger of its own instead of having to branch on `message_type`
inside a generic message-received flow.

Run context: `{from, message_id, message_type: "interactive", timestamp,
interactive: {type: "button_reply"|"list_reply", id, title}}` - `id` is
whichever id you set on the button/list-row you sent (see
`whatsapp_send_interactive_buttons.py`/`whatsapp_send_interactive_list.py`),
the natural field to branch a `condition.field_compare`/
`condition.multi_branch` node on.
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

NODE_TYPE = "whatsapp.interactive_reply_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "message_id": {"type": "string"},
        "interactive": {
            "type": "object",
            "properties": {
                "type": {"type": "string"},
                "id": {"type": "string"},
                "title": {"type": "string"},
            },
        },
    },
}


class WhatsAppInteractiveReplyReceivedConfig(BaseModel):
    description: str | None = Field(default=None, max_length=200)


class WhatsAppInteractiveReplyReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "WhatsApp Button/List Reply Received"
    description = (
        "Fires when a customer taps a quick-reply button or selects a list item from a message "
        "this business sent. Run context includes interactive.id/title for the tapped option."
    )
    config_model = WhatsAppInteractiveReplyReceivedConfig
    required_connector_type_key = "whatsapp"
    output_schema = _OUTPUT_SCHEMA
    applicable_purposes = ["automation"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = WhatsAppInteractiveReplyReceivedExecutor()
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
