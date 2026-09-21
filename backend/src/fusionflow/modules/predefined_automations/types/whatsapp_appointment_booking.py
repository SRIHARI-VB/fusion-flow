"""`whatsapp.appointment_booking` — the flagship predefined automation for
WhatsApp: when a customer's message matches a configured keyword, send an
automatic acknowledgement and raise a support ticket so staff can confirm
an actual time slot.

Config shape (the wizard's own structured answers, stored verbatim on
`PredefinedAutomation.config` for re-editing):
    {
      "trigger_keywords": ["book", "appointment"],  # non-empty, required
      "matching_method": "contains",                 # exact|contains|starts_with|ends_with
      "service_name": "Consultation",                 # required
      "duration_minutes": 30,                          # required, > 0
      "confirmation_message": "Thanks for your interest ..." | null,
                                                        # null/empty falls back to a generated default
    }

Deliberately an intake-and-handoff automation, not a self-service slot
picker: this codebase's workflow engine has no availability/calendar-
conflict-checking primitive yet, and free-text-capturing the customer's
preferred time via `whatsapp.ask_question` would need to feed that answer
into a real slot-booking decision this automation doesn't make - `service.
py`'s reasoning for scoping the Instagram flagship applies here too
(ship the honestly-buildable version now, not a half-working slot engine).
What this DOES automate for real: instant acknowledgement (so the customer
isn't left waiting) plus a `create_ticket` handoff carrying the service
name/duration/customer's WhatsApp number, so staff finalize the actual
appointment time through the existing ticket workflow rather than the
customer never hearing back until a human happens to notice the message.
If a Google Calendar connector is connected, staff still create the real
calendar event themselves once a time is agreed - this automation does not
guess a slot and silently book it.

Generated graph shape: trigger (`whatsapp.message_received`) -> an
OR-chained sequence of `condition.field_compare` nodes (one per configured
keyword - see `graph_helpers.build_keyword_condition_chain`, reused
verbatim from `instagram_comment_automation.py`) -> `connector.action`
(send the confirmation text) -> `create_ticket` (handoff), chained
sequentially.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import build_keyword_condition_chain
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "whatsapp.appointment_booking"

MatchingMethod = Literal["exact", "contains", "starts_with", "ends_with"]

_METHOD_TO_OPERATOR: dict[MatchingMethod, str] = {
    "exact": "eq",
    "contains": "contains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
}


class WhatsAppAppointmentBookingConfig(BaseModel):
    trigger_keywords: list[str] = Field(min_length=1)
    matching_method: MatchingMethod = "contains"
    service_name: str = Field(min_length=1, max_length=200)
    duration_minutes: int = Field(gt=0)
    confirmation_message: str | None = None


def _default_confirmation_message(service_name: str, duration_minutes: int) -> str:
    return (
        f"Thanks for your interest in booking a {service_name} ({duration_minutes} min)! "
        "Our team will reach out shortly to confirm a time that works for you."
    )


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = WhatsAppAppointmentBookingConfig.model_validate(config)
    instance_id = str(connector_instance_id)
    confirmation_text = parsed.confirmation_message or _default_confirmation_message(
        parsed.service_name, parsed.duration_minutes
    )

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {"nodeType": "whatsapp.message_received", "label": "Message Received", "config": {}},
        }
    ]
    edges: list[dict[str, Any]] = []
    x = 780  # condition chain occupies x=260..~780 depending on keyword count; actions start past it

    action_nodes: list[dict[str, Any]] = [
        {
            "id": "action-confirm",
            "type": "action",
            "position": {"x": x, "y": 0},
            "data": {
                "nodeType": "connector.action",
                "label": "Send Confirmation",
                "config": {
                    "connector_instance_id": instance_id,
                    "action": "send_text_message",
                    "params": {"to": "{{trigger.from}}", "body": confirmation_text},
                },
            },
        },
        {
            "id": "action-ticket",
            "type": "action",
            "position": {"x": x + 260, "y": 0},
            "data": {
                "nodeType": "create_ticket",
                "label": "Raise Booking Ticket",
                "config": {
                    "subject": (
                        f"Appointment request: {parsed.service_name} ({parsed.duration_minutes} min) - "
                        "from {{trigger.from}}"
                    )
                },
            },
        },
    ]

    # Action nodes are unrestricted (no declared output handles), so they
    # chain sequentially via a plain default-handle edge - only the FIRST
    # one is the condition chain's convergence target.
    nodes.append(action_nodes[0])
    nodes.append(action_nodes[1])
    edges.append(
        {
            "id": f"e-{action_nodes[0]['id']}-{action_nodes[1]['id']}",
            "source": action_nodes[0]["id"],
            "target": action_nodes[1]["id"],
        }
    )

    operator = _METHOD_TO_OPERATOR[parsed.matching_method]
    chain_nodes, chain_edges = build_keyword_condition_chain(
        trigger_node_id="trigger",
        field_path="trigger.text",
        keywords=parsed.trigger_keywords,
        operator=operator,
        on_match_target_id=action_nodes[0]["id"],
        start_x=260,
    )
    nodes.extend(chain_nodes)
    edges.extend(chain_edges)

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="whatsapp",
        label="Appointment Booking",
        description=(
            "Auto-acknowledge a customer asking to book an appointment and raise a ticket for "
            "staff to confirm the actual time."
        ),
        build_graph=build_graph,
    )
)
