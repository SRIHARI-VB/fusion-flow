"""`tickets.add_note` — appends a message to an *already-created* ticket's
thread via `modules/tickets/service.py::add_message`.

`create_ticket`/`records.upsert` (module=tickets, operation=create) both
cap `subject` at 300 characters, far too short to hold every detail a
conversation actually collected (name, concern, contact info, timestamps,
the customer's raw message text, ...). This node is the deliberate
follow-up step for that gap: a thin wrapper around `add_message` (same
"call the service directly, don't duplicate its logic" shape as
`instagram.find_or_create_customer` below), so a workflow author chains
`records.upsert` (create) -> `tickets.add_note` (`ticket_id` templated off
`{{create-ticket-xyz.item.id}}`, per that node's `{"item": {...}}` output
shape) to log the full detail block as a normal `TicketMessage` thread
entry instead of squeezing it into `subject`. It does not check the
ticket exists first - `add_message`'s own FK constraint on `ticket_id`
surfaces a clear DB error for that (a config mistake, not a normal runtime
path), same reasoning `record_upsert.py`'s update-path 404 doesn't apply
here since there's no adapter read-back involved.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from fusionflow.modules.tickets import service as tickets_service
from fusionflow.modules.tickets.models import TicketMessageAuthorType
from fusionflow.modules.tickets.schemas import TicketMessageCreate
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate

_OUTPUT_SCHEMA = {"type": "object", "properties": {"message_id": {"type": "string"}}}


class AddTicketNoteConfig(BaseModel):
    ticket_id: str = Field(
        min_length=1,
        description="The ticket to append to, typically '{{create-ticket-xyz.item.id}}'.",
    )
    body: str = Field(
        min_length=1,
        description="The full detail block to log to the ticket's thread - may reference the run context.",
    )
    author_type: TicketMessageAuthorType = Field(default=TicketMessageAuthorType.SYSTEM)


class AddTicketNoteExecutor(NodeExecutor):
    node_type = "tickets.add_note"
    kind = "action"
    category = "Support"
    label = "Add Ticket Note"
    description = "Appends a message to an existing ticket's thread - use this to log full conversation details a 300-character subject can't hold."
    config_model = AddTicketNoteConfig
    required_connector_type_key = "tickets"
    applicable_purposes = ["automation", "broadcast"]
    output_schema = _OUTPUT_SCHEMA
    # A transient DB hiccup during the insert is the retry target here -
    # same reasoning/values as `create_ticket.py` and
    # `instagram_find_or_create_customer.py` for this class of operation.
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = AddTicketNoteConfig.model_validate(context.config)
        ticket_id_raw = interpolate(config.ticket_id, context.variables)
        body = interpolate(config.body, context.variables)

        try:
            ticket_id = uuid.UUID(ticket_id_raw)
        except ValueError:
            return Failure(f"ticket_id {ticket_id_raw!r} is not a valid UUID")

        message = await tickets_service.add_message(
            context.session,
            context.tenant_id,
            ticket_id,
            TicketMessageCreate(author_type=config.author_type, body=body),
        )
        return Success(output={"message_id": str(message.id)})


node_executor_registry.register(AddTicketNoteExecutor())
