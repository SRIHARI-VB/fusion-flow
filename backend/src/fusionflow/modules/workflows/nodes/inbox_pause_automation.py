"""`inbox.pause_automation` — the `instagram.handoff_automation` (and any
future channel's) "human handoff" action: marks the run's originating
Unified Inbox `Conversation` as `automation_paused`, so the outbox
poller's dispatch gate (`engine/outbox_poller.py::_conversation_automation_is_paused`)
skips starting a new run for this conversation's future messages until a
human agent clears it from the Inbox UI (`POST /inbox/conversations/{id}/
automation-paused`).

Not a `connector.action` node - Inbox is tenant-owned, not a per-provider
adapter capability, so this is its own generic node type instead of
another `perform_action` branch. Only meaningful for DM-shaped triggers
(anything whose `trigger.from` resolves to an Inbox `Conversation` - a
comment or mention trigger has no such conversation, and this node is a
silent no-op there rather than a hard failure - see
`inbox_service.pause_automation_for_contact`'s docstring).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from fusionflow.modules.inbox import service as inbox_service
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)

_OUTPUT_SCHEMA = {"type": "object", "properties": {"paused": {"type": "boolean"}}}


class InboxPauseAutomationConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)


class InboxPauseAutomationExecutor(NodeExecutor):
    node_type = "inbox.pause_automation"
    kind = "action"
    category = "Inbox"
    label = "Pause Automation for This Conversation"
    description = (
        "Marks this conversation as needing a human, so no predefined automation replies to it "
        "again until an agent resumes it from the Inbox."
    )
    config_model = InboxPauseAutomationConfig
    output_schema = _OUTPUT_SCHEMA

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = InboxPauseAutomationConfig.model_validate(context.config)
        external_contact_id = context.variables.get("trigger", {}).get("from")
        if not external_contact_id:
            # Wizard/config mistake (this node used on a non-DM automation
            # type) or an edge case, not a run-breaking error - see module
            # docstring.
            return Success(output={"paused": False})
        await inbox_service.pause_automation_for_contact(
            context.session,
            tenant_id=context.tenant_id,
            connector_instance_id=uuid.UUID(config.connector_instance_id),
            external_contact_id=external_contact_id,
        )
        return Success(output={"paused": True})


node_executor_registry.register(InboxPauseAutomationExecutor())
