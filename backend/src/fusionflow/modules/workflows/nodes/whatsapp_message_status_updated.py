"""`whatsapp.message_status_updated` — fires on every delivery-status
transition (sent/delivered/read/failed) for a message this business sent,
including template sends. The trigger that makes marketing/utility
delivery tracking possible - build a workflow that logs/alerts on
`status == "failed"` for a marketing campaign, for example.

`WhatsAppAdapter.handle_webhook` publishes one event per `.statuses`
callback, deduped on `f"{message_id}:{status}"` (not just `message_id`) -
so the natural sent -> delivered -> read progression fires this trigger
once per distinct status, never collapsed into one.

Run context: `{message_id, status, recipient_id, timestamp, error}`
(`error` is `None` unless `status == "failed"`).
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

NODE_TYPE = "whatsapp.message_status_updated"


class WhatsAppMessageStatusUpdatedConfig(BaseModel):
    description: str | None = Field(default=None, max_length=200)


class WhatsAppMessageStatusUpdatedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messaging"
    label = "WhatsApp Message Status Updated"
    description = (
        "Fires on every delivery-status transition (sent/delivered/read/failed) for a message "
        "this business sent, including template sends - the basis for delivery tracking."
    )
    config_model = WhatsAppMessageStatusUpdatedConfig

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = WhatsAppMessageStatusUpdatedExecutor()
node_executor_registry.register(_executor)
trigger_registry.register(
    TriggerDefinition(
        trigger_type=_executor.node_type,
        category=_executor.category,
        label=_executor.label,
        description=_executor.description,
        config_model=_executor.config_model,
    )
)
