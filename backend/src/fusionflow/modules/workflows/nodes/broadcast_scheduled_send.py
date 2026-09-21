"""`broadcast.scheduled_send` — the trigger a recurring/scheduled bulk-send
workflow starts from. Unlike every other trigger (`whatsapp.message_received`,
`order.created`, ...), which fires from a live domain event via the
transactional-outbox pattern, this one fires from `engine/schedule_poller.py`
polling `models.WorkflowSchedule.next_run_at` — the recipient list itself is
never authored on the node; it is resolved at fire time from the owning
schedule's own `recipient_source` (a static phone-number list, or a live
module query) and handed to the run as `trigger_payload={"recipients": [...]}`.

Declaring `recipients` in `output_schema` (rather than leaving it
uncatalogued) is what lets `flow.loop`'s `items_path` field-suggestion/
insert-variable picker discover `trigger.recipients` downstream — the same
mechanism any other trigger's declared output already powers (see
`engine/registry.py::NodeTypeMeta.output_schema`'s docstring).

`applicable_purposes = ["broadcast"]` (the "workflow purpose" tag) keeps
this trigger out of an "automation"-purpose workflow's palette, and the
symmetric `applicable_purposes = ["automation"]` set on the five
domain-event triggers keeps them out of a "broadcast"-purpose workflow's
palette — see `service.list_node_types_with_templates`'s purpose filter.
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

NODE_TYPE = "broadcast.scheduled_send"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "recipients": {"type": "array", "items": {"type": "string"}},
    },
}


class BroadcastScheduledSendConfig(BaseModel):
    """No required fields — the recipient list is supplied at run-start
    time via `trigger_payload` by `engine/schedule_poller.py`, resolved from
    the owning `WorkflowSchedule.recipient_source` at fire time, not
    authored on this node. `description` is just the author's own note."""

    description: str | None = Field(default=None, max_length=200)


class BroadcastScheduledSendExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "Scheduled/Bulk Send"
    description = (
        "Fires on a recurring schedule (or a one-off future instant) configured on this "
        "workflow's schedule. Run context is seeded with 'recipients' - a phone-number list "
        "resolved at fire time from the schedule's static list or a live module query."
    )
    config_model = BroadcastScheduledSendConfig
    output_schema = _OUTPUT_SCHEMA
    icon = "calendar"
    palette_group = "Triggers"
    applicable_purposes = ["broadcast"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        # `variables["trigger"]` was seeded by run_loop.execute_run from the
        # `{"recipients": [...]}` payload `schedule_poller._fire_schedule`
        # passed to `execute_run` - same pass-through shape every other
        # trigger executor in this package uses.
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = BroadcastScheduledSendExecutor()
node_executor_registry.register(_executor)
trigger_registry.register(
    TriggerDefinition(
        trigger_type=_executor.node_type,
        category=_executor.category,
        label=_executor.label,
        description=_executor.description,
        config_model=_executor.config_model,
        output_schema=_executor.output_schema,
        icon=_executor.icon,
        palette_group=_executor.palette_group,
        applicable_purposes=_executor.applicable_purposes,
    )
)
