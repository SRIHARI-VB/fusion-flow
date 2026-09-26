"""`calendar.parse_mode_choice` — the safe consumer half of the
online/offline postback sent after a calendar slot is picked, payload
`"MODE:<online|offline>|<context>|<start_iso>|<end_iso>|<label>"`.

A slot's start/end/label (and the caller's opaque `context`, e.g. which
day/concern chain led here) are already known by the time the "online or
offline?" question is asked, but the run that resolved them ends the
moment that message is sent - the next run only has whatever the tapped
button's payload carries. Rather than re-deriving the slot from scratch,
the "online or offline?" step's own buttons simply carry the already-
resolved slot + context + `calendar.parse_slot_choice`'s own `label`
forward verbatim, so a later confirmation message can restate a friendly
time ("10:00 AM - 10:30 AM") without this node reformatting timestamps
itself. Same "malformed/not found resolves to a plain result, never a
`Failure`" convention as `calendar.parse_slot_choice` and
`module.get_from_choice_payload`, so it's safe to sit behind a postback-
routing chain's fallback.
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

_PREFIX = "MODE:"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "mode": {"type": ["string", "null"]},
        "context": {"type": ["string", "null"]},
        "start_iso": {"type": ["string", "null"]},
        "end_iso": {"type": ["string", "null"]},
        "label": {"type": ["string", "null"]},
    },
}

_NOT_FOUND: dict[str, Any] = {
    "found": False,
    "mode": None,
    "context": None,
    "start_iso": None,
    "end_iso": None,
    "label": None,
}  # type: ignore[name-defined]


class ParseModeChoiceConfig(BaseModel):
    payload: str = Field(min_length=1, description="Usually '{{trigger.payload}}'.")


class ParseModeChoiceExecutor(NodeExecutor):
    node_type = "calendar.parse_mode_choice"
    kind = "action"
    category = "Data"
    label = "Parse Online/Offline Choice"
    description = "Parses the post-slot-pick online/offline postback back into mode + the carried slot/context - resolves to 'not found' instead of failing the run for anything malformed."
    config_model = ParseModeChoiceConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = False

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ParseModeChoiceConfig.model_validate(context.config)
        raw = interpolate(config.payload, context.variables)

        if not isinstance(raw, str) or not raw.startswith(_PREFIX):
            return Success(output=dict(_NOT_FOUND))

        body = raw[len(_PREFIX) :]
        parts = body.split("|")
        if len(parts) != 5:
            return Success(output=dict(_NOT_FOUND))
        mode, context_str, start_str, end_str, label_str = parts
        if mode not in ("online", "offline") or not start_str or not end_str:
            return Success(output=dict(_NOT_FOUND))

        try:
            datetime.fromisoformat(start_str)
            datetime.fromisoformat(end_str)
        except ValueError:
            return Success(output=dict(_NOT_FOUND))

        return Success(
            output={
                "found": True,
                "mode": mode,
                "context": context_str,
                "start_iso": start_str,
                "end_iso": end_str,
                "label": label_str or None,
            }
        )


node_executor_registry.register(ParseModeChoiceExecutor())
