"""`schedule.is_direct_booking_day` — "does this tenant's configured
`direct_booking_weekdays` list include the weekday `date_offset_days` from
today (in `timezone`)". Also resolves and returns that target date/weekday
so a workflow author doesn't need a second node just to know what day
they're actually talking about.

A dedicated node rather than a `condition.field_compare` with some new
"in" operator: the *weekday name* itself has to be computed from "today +
offset, in this timezone" first (there's nothing else in this engine that
already exposes "what weekday is it"), and bundling that computation with
the membership check avoids a workflow author needing two nodes wired
together just to ask one question.

Fails CLOSED, not open: if `direct_booking_weekdays` doesn't resolve to a
real list (e.g. malformed template, settings row missing the field), this
resolves to `is_direct_booking_day: False` - the existing ticket-based
flow, not an accidental "treat every day as direct-booking" - see the
config field's own docstring for why.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import resolve_template_value

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "is_direct_booking_day": {"type": "boolean"},
        "weekday": {"type": "string"},
        "date": {"type": "string", "description": "YYYY-MM-DD, in the given timezone."},
    },
}

_WEEKDAY_NAMES = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class IsDirectBookingDayConfig(BaseModel):
    date_offset_days: int = Field(default=0, ge=0, description="0 = today, 1 = tomorrow, in `timezone`.")
    direct_booking_weekdays: str = Field(
        description=(
            "Templated list reference, e.g. "
            "'{{business-settings-pb.item.payload.direct_booking_weekdays}}' - must be a WHOLE-template "
            "reference (nothing else in the string) for the templating engine to preserve the real list "
            "type rather than stringifying it. Resolves to 'no direct-booking days' (fails closed) if "
            "this doesn't come back as an actual list."
        )
    )
    timezone: str = Field(default="Asia/Kolkata", description="IANA timezone name.")

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {value!r}") from exc
        return value


class IsDirectBookingDayExecutor(NodeExecutor):
    node_type = "schedule.is_direct_booking_day"
    kind = "action"
    category = "Scheduling"
    label = "Is Direct-Booking Day?"
    description = "Resolves today+offset's weekday/date in a timezone and checks it against the tenant's configured direct-booking weekdays."
    config_model = IsDirectBookingDayConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = False

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = IsDirectBookingDayConfig.model_validate(context.config)
        tz = ZoneInfo(config.timezone)
        target = datetime.now(tz) + timedelta(days=config.date_offset_days)
        weekday = _WEEKDAY_NAMES[target.weekday()]

        resolved = resolve_template_value(config.direct_booking_weekdays, context.variables)
        allowed_days = (
            {str(d).strip().lower() for d in resolved} if isinstance(resolved, list) else set()
        )

        return Success(
            output={
                "is_direct_booking_day": weekday in allowed_days,
                "weekday": weekday,
                "date": target.strftime("%Y-%m-%d"),
            }
        )


node_executor_registry.register(IsDirectBookingDayExecutor())
