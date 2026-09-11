"""`create_ticket` — creates a support ticket via
`modules/tickets/service.py::create_ticket`.

`subject`/`customer_id` support the same `{{dot.path}}` interpolation
against the running variable context as `send_whatsapp_message.py` (see
that file's docstring for why this is the same dot-path addressing
`condition.field_compare` already established, not a new templating
syntax).
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.tickets import service as tickets_service
from fusionflow.modules.tickets.schemas import TicketCreate
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)

_TEMPLATE_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")

_OUTPUT_SCHEMA = {"type": "object", "properties": {"ticket_id": {"type": "string"}}}


def _resolve_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _interpolate(template: str, variables: dict[str, Any]) -> str:
    def _replace(match: "re.Match[str]") -> str:
        value = _resolve_path(variables, match.group(1))
        return "" if value is None else str(value)

    return _TEMPLATE_RE.sub(_replace, template)


class CreateTicketConfig(BaseModel):
    subject: str = Field(
        min_length=1,
        max_length=300,
        description="Ticket subject. May reference the run context, e.g. 'WhatsApp: {{trigger.text}}'.",
    )
    customer_id: str | None = Field(
        default=None,
        description=(
            "Optional existing customer id (UUID, may reference the run context). "
            "Leave unset when the triggering event doesn't identify a known customer."
        ),
    )


class CreateTicketExecutor(NodeExecutor):
    node_type = "create_ticket"
    kind = "action"
    category = "Support"
    label = "Create Ticket"
    description = "Creates a support ticket for this business, optionally linked to an existing customer."
    config_model = CreateTicketConfig
    required_connector_type_key = "tickets"
    output_schema = _OUTPUT_SCHEMA
    # A transient DB hiccup during the insert is the retry target here -
    # see send_whatsapp_message.py's matching comment for why the service
    # call below is deliberately left un-caught rather than turned into an
    # immediate, permanent `Failure`.
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = CreateTicketConfig.model_validate(context.config)
        subject = _interpolate(config.subject, context.variables)

        customer_id: uuid.UUID | None = None
        if config.customer_id:
            resolved = _interpolate(config.customer_id, context.variables)
            if resolved:
                try:
                    customer_id = uuid.UUID(resolved)
                except ValueError:
                    return Failure(f"customer_id {resolved!r} is not a valid UUID")

        ticket = await tickets_service.create_ticket(
            context.session,
            context.tenant_id,
            TicketCreate(subject=subject, customer_id=customer_id),
        )

        return Success(output={"ticket_id": str(ticket.id)})


node_executor_registry.register(CreateTicketExecutor())
