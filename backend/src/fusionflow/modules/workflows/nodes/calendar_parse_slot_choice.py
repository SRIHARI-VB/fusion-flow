"""`calendar.parse_slot_choice` — the safe consumer half of
`instagram.ask_calendar_slot`'s `"SLOT:<context>|<start_iso>|<end_iso>"`
postback payload.

Same "no-match-is-not-an-error" convention as
`module.get_from_choice_payload`: a malformed/missing/unparseable payload
resolves to `{"found": False, ...}` rather than failing the run, so it's
safe to sit behind a postback-routing chain's fallback without risking
`ChildExecutionError`/`RunStatus.FAILED` on a stale or unrelated tap.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate

_PREFIX = "SLOT:"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "start_iso": {"type": ["string", "null"]},
        "end_iso": {"type": ["string", "null"]},
        "label": {"type": ["string", "null"]},
        "context": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"], "description": "YYYY-MM-DD (date part of start_iso) - a 'date'-typed custom field rejects a full datetime string with a non-midnight time."},
    },
}


def _format_12h(dt: datetime) -> str:
    """`"2:30 PM"`, no leading zero - `%-I` is a Unix-only strftime
    extension (works on this app's Linux/Vercel runtime, but raises
    `ValueError: Invalid format string` on Windows, where this couldn't
    even be locally tested otherwise). `%I` + manual lstrip is portable."""
    return dt.strftime("%I:%M %p").lstrip("0")

_NOT_FOUND: dict[str, Any] = {
    "found": False,
    "start_iso": None,
    "end_iso": None,
    "label": None,
    "context": None,
    "date": None,
}  # type: ignore[name-defined]


class ParseSlotChoiceConfig(BaseModel):
    payload: str = Field(min_length=1, description="Usually '{{trigger.payload}}'.")


class ParseSlotChoiceExecutor(NodeExecutor):
    node_type = "calendar.parse_slot_choice"
    kind = "action"
    category = "Data"
    label = "Parse Calendar Slot Choice"
    description = "Parses an instagram.ask_calendar_slot-style postback payload back into a start/end time - resolves to 'not found' instead of failing the run for anything malformed."
    config_model = ParseSlotChoiceConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = False

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ParseSlotChoiceConfig.model_validate(context.config)
        raw = interpolate(config.payload, context.variables)

        if not isinstance(raw, str) or not raw.startswith(_PREFIX):
            return Success(output=dict(_NOT_FOUND))

        body = raw[len(_PREFIX) :]
        parts = body.split("|")
        if len(parts) != 3:
            return Success(output=dict(_NOT_FOUND))
        context_str, start_str, end_str = parts
        if not start_str or not end_str:
            return Success(output=dict(_NOT_FOUND))

        try:
            start_dt = datetime.fromisoformat(start_str)
            end_dt = datetime.fromisoformat(end_str)
        except ValueError:
            return Success(output=dict(_NOT_FOUND))

        label = f"{_format_12h(start_dt)} - {_format_12h(end_dt)}"
        return Success(
            output={
                "found": True,
                "start_iso": start_str,
                "end_iso": end_str,
                "label": label,
                "context": context_str,
                "date": start_dt.date().isoformat(),
            }
        )


node_executor_registry.register(ParseSlotChoiceExecutor())
