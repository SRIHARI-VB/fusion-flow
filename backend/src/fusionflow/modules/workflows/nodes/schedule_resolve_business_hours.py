"""`schedule.resolve_business_hours` - resolves a relative day reference
("now"/"today"/"tomorrow"/a weekday name) plus an optional named
time-of-day window against a tenant-configured set of business hours,
using the real wall-clock date/time in a configured IANA timezone
(default `Asia/Kolkata`).

Purely deterministic and self-contained, same shape as `data_transform.py`/
`flow_delay.py`: a Pydantic `config_model`, one `execute`, a plain
`Success(output=...)` - no AI, no network calls, no connector. The
business's opening hours (which weekdays are closed, open/close time,
optionally named windows like morning/afternoon/evening) live entirely in
this node's config, so the same node type serves any tenant's day/
time-window booking logic rather than one clinic's hardcoded hours.

Two independent things this node answers, both from one config:

1. "Resolve a relative day reference" - `day_reference: "today" |
   "tomorrow" | <weekday name>` (or the default `"now"`, meaning "today,
   as of right now") turns into an actual calendar date, whether that
   date falls on a closed weekday, whether a requested named time-of-day
   window has already fully elapsed today, and the next open day/date to
   offer as an alternative when the requested slot is invalid.

2. "Is the business open at this exact instant" - `is_open_now` in the
   output is always computed against the real current time regardless of
   `day_reference`, so a workflow that just needs an immediate "are you
   open right now" branch (e.g. an emergency-reply flow choosing "reply
   during hours" vs "reply outside hours") can wire a `condition.
   field_compare` off `is_open_now` alone, using this node's default
   `day_reference="now"` and no `time_of_day` at all - no day/time-of-day
   reference needs to be configured for that case.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)

Weekday = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
#: Canonical lowercase weekday names, Monday-first, matching
#: `date.strftime("%A").lower()` - the single source of truth both the
#: config's `closed_weekdays` and a `day_reference` weekday name are
#: validated against.
_WEEKDAY_NAMES: list[str] = [name.lower() for name in calendar.day_name]

DayReference = Literal[
    "now", "today", "tomorrow", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"
]


def _parse_hhmm(value: str) -> time:
    try:
        hour_str, minute_str = value.split(":", 1)
        return time(hour=int(hour_str), minute=int(minute_str))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"expected an 'HH:MM' 24-hour time string, got {value!r}") from exc


class TimeWindow(BaseModel):
    """A named sub-window of the day (e.g. "morning") an author can offer
    a customer as a coarser choice than an exact time - purely a labelled
    `[start, end)` range within the business's overall open/close hours."""

    start: str = Field(description="24-hour 'HH:MM', e.g. '09:00'.")
    end: str = Field(description="24-hour 'HH:MM', e.g. '12:00'.")

    @field_validator("start", "end")
    @classmethod
    def _validate_hhmm(cls, value: str) -> str:
        _parse_hhmm(value)
        return value


class BusinessHoursConfig(BaseModel):
    timezone: str = Field(
        default="Asia/Kolkata", description="IANA timezone name the business's hours are defined in."
    )
    open_time: str = Field(default="09:00", description="24-hour 'HH:MM' the business opens each open day.")
    close_time: str = Field(default="18:00", description="24-hour 'HH:MM' the business closes each open day.")
    closed_weekdays: list[Weekday] = Field(
        default_factory=list,
        description="Lowercase weekday names the business is fully closed on, e.g. ['sunday'].",
    )
    time_windows: dict[str, TimeWindow] = Field(
        default_factory=dict,
        description="Named time-of-day windows (e.g. 'morning'/'afternoon'/'evening') a 'time_of_day' reference can name.",
    )
    day_reference: DayReference = Field(
        default="now",
        description=(
            "'now' - immediate 'is it open right now' check, no date resolution beyond today. "
            "'today'/'tomorrow' - relative day. A weekday name - the next occurrence of that "
            "weekday, today included if today already is that weekday."
        ),
    )
    time_of_day: str | None = Field(
        default=None, description="A key into 'time_windows' to check - must match one of its keys if set."
    )

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {value!r}") from exc
        return value

    @field_validator("open_time", "close_time")
    @classmethod
    def _validate_hhmm(cls, value: str) -> str:
        _parse_hhmm(value)
        return value


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "resolved_date": {"type": "string", "description": "ISO 'YYYY-MM-DD' of the resolved day_reference."},
        "resolved_date_display": {"type": "string", "description": "e.g. 'Monday, 15 September 2026'."},
        "resolved_weekday": {"type": "string"},
        "is_closed": {"type": "boolean", "description": "Whether resolved_date is a closed_weekdays day."},
        "time_of_day_passed": {
            "type": ["boolean", "null"],
            "description": "Null if no time_of_day was configured; else whether that window has already fully elapsed for today.",
        },
        "is_open_now": {"type": "boolean", "description": "Open at the real current instant, independent of day_reference."},
        "next_open_day": {"type": "string"},
        "next_open_date": {"type": "string"},
        "next_open_date_display": {"type": "string"},
    },
}


def _next_occurrence(start: date, weekday_name: str) -> date:
    """The next date on/after `start` whose weekday is `weekday_name`
    (today included if it already matches)."""
    target_index = _WEEKDAY_NAMES.index(weekday_name)
    offset = (target_index - start.weekday()) % 7
    return start + timedelta(days=offset)


def _next_open_day(after: date, closed_weekdays: set[str]) -> date:
    """First date strictly after `after` whose weekday isn't closed. Scans
    at most 8 days ahead - if every weekday were closed this would still
    terminate (falls through to `after + timedelta(days=8)`), avoiding an
    infinite loop for a (nonsensical but not rejected) "closed every day"
    config."""
    candidate = after
    for _ in range(8):
        candidate = candidate + timedelta(days=1)
        if candidate.strftime("%A").lower() not in closed_weekdays:
            return candidate
    return candidate


def _display(d: date) -> str:
    return f"{calendar.day_name[d.weekday()]}, {d.day} {calendar.month_name[d.month]} {d.year}"


class ResolveBusinessHoursExecutor(NodeExecutor):
    node_type = "schedule.resolve_business_hours"
    kind = "action"
    category = "Scheduling"
    label = "Resolve Business Hours"
    description = (
        "Resolves a relative day (now/today/tomorrow/a weekday) and optional named time-of-day "
        "window against configured business hours - open/closed status, whether the window has "
        "already passed today, whether it's open right now, and the next open day."
    )
    config_model = BusinessHoursConfig
    output_schema = _OUTPUT_SCHEMA

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = BusinessHoursConfig.model_validate(context.config)
        closed_weekdays = set(config.closed_weekdays)

        tz = ZoneInfo(config.timezone)
        now = datetime.now(tz)
        today = now.date()

        if config.day_reference in ("now", "today"):
            resolved_date = today
        elif config.day_reference == "tomorrow":
            resolved_date = today + timedelta(days=1)
        else:
            resolved_date = _next_occurrence(today, config.day_reference)

        resolved_weekday = resolved_date.strftime("%A").lower()
        is_closed = resolved_weekday in closed_weekdays

        time_of_day_passed: bool | None = None
        if config.time_of_day is not None:
            window = config.time_windows.get(config.time_of_day)
            if window is None:
                return Success(
                    output={
                        "error": f"time_of_day {config.time_of_day!r} is not one of this node's configured time_windows"
                    }
                )
            if resolved_date == today:
                window_end = _parse_hhmm(window.end)
                time_of_day_passed = now.time() >= window_end
            else:
                # resolved_date is strictly in the future - a window on a
                # future date can never have "already passed".
                time_of_day_passed = False

        is_open_now = today.strftime("%A").lower() not in closed_weekdays and (
            _parse_hhmm(config.open_time) <= now.time() < _parse_hhmm(config.close_time)
        )

        next_open = _next_open_day(resolved_date, closed_weekdays)

        return Success(
            output={
                "resolved_date": resolved_date.isoformat(),
                "resolved_date_display": _display(resolved_date),
                "resolved_weekday": resolved_weekday,
                "is_closed": is_closed,
                "time_of_day_passed": time_of_day_passed,
                "is_open_now": is_open_now,
                "next_open_day": next_open.strftime("%A").lower(),
                "next_open_date": next_open.isoformat(),
                "next_open_date_display": _display(next_open),
            }
        )


node_executor_registry.register(ResolveBusinessHoursExecutor())
