"""`tickets.get_latest_for_customer` — the "what's the status of my most
recent request?" answer: looks up a customer's newest `Ticket` (across
every flow that creates one - a booking, a reschedule, a Sunday request,
a fallback query, ...), returned as one flat object.

Exists because `records.query` (module=tickets, operation=list) returns
`{"items": [...], "count": N}` - a *list* - and the templating engine's
`resolve_path` only ever traverses dicts (`isinstance(current, dict)`),
so `{{some-query-node.items.0.subject}}` can never resolve; there is no
"list, then take the first element" available to a workflow author
anywhere in this engine today. Same reasoning, same fix shape, as
`instagram.find_or_create_customer`/`whatsapp.find_or_create_customer`
(a customer lookup that could return 0 or 1 rows, flattened to one
always-consistent output either way) - this is that same pattern applied
to "the newest of possibly several tickets" instead of "a customer
looked up by an external id".
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from fusionflow.modules.tickets import service as tickets_service
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "subject": {"type": ["string", "null"]},
        "status": {"type": ["string", "null"]},
        "priority": {"type": ["string", "null"]},
    },
}


class GetLatestTicketConfig(BaseModel):
    customer_id: str = Field(
        min_length=1,
        description="Whose newest ticket to look up, typically '{{find-or-create-customer-xyz.customer.id}}'.",
    )


class GetLatestTicketForCustomerExecutor(NodeExecutor):
    node_type = "tickets.get_latest_for_customer"
    kind = "action"
    category = "Support"
    label = "Get Latest Ticket for Customer"
    description = (
        "Looks up a customer's most recently created ticket (any status/priority), flattened to one "
        "object - 'found' is False (not an error) when they have none yet."
    )
    config_model = GetLatestTicketConfig
    required_connector_type_key = "tickets"
    applicable_purposes = ["automation", "broadcast"]
    output_schema = _OUTPUT_SCHEMA
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = GetLatestTicketConfig.model_validate(context.config)
        customer_id_raw = interpolate(config.customer_id, context.variables)

        try:
            customer_id = uuid.UUID(customer_id_raw)
        except ValueError:
            return Failure(f"customer_id {customer_id_raw!r} is not a valid UUID")

        tickets = await tickets_service.list_tickets(
            context.session, context.tenant_id, customer_id=customer_id, limit=1
        )
        if not tickets:
            return Success(output={"found": False, "subject": None, "status": None, "priority": None})

        latest = tickets[0]
        return Success(
            output={
                "found": True,
                "subject": latest.subject,
                "status": latest.status.value,
                "priority": latest.priority,
            }
        )


node_executor_registry.register(GetLatestTicketForCustomerExecutor())
