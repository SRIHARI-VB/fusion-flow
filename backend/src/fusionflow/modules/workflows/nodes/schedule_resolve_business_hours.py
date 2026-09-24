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

Templating: `open_time`/`close_time`/`break_start`/`break_end`/each
`closed_weekdays` entry/each `time_windows[name].start`/`.end` value are
run through `engine.templating.interpolate` against `context.variables`
before `BusinessHoursConfig.model_validate` - see `_interpolate_config`'s
docstring for why that's a fixed, opt-in field list rather than a blind
recursive walk of `context.config`. This lets a tenant's actual hours
live in a `business_objects` "business_settings" record (looked up by an
earlier node) and be referenced here as e.g.
"{{business-settings.item.payload.open_time}}", instead of every
workflow hardcoding that tenant's hours as literal config. A plain
literal like "09:00" with no {{...}} in it is untouched by `interpolate`
(no match, no substitution), so this is fully backward compatible with
every config written before this change.

Lunch-break support: `break_start`/`break_end` (both optional, both-or-
neither) mark one daily window the business is closed even though it
falls inside `open_time`/`close_time` - folded into `is_open_now` only.
Deliberately NOT subtracted from `time_windows`: a tenant whose
"afternoon" `TimeWindow` happens to straddle their break is assumed to
have defined that window on purpose (e.g. as a coarse customer-facing
label), and auto-splitting it would silently change what "afternoon"
means out from under them. A tenant who wants a break-aware named window
should define non-overlapping `time_windows` themselves. `is_open_now` is
the one output that always reflects the literal true instant, so that's
the only place the break is enforced.
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate

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


def _is_template(value: str) -> bool:
    """Whether `value` is (or contains) a `{{dot.path}}` reference rather
    than a literal - `BusinessHoursConfig` is validated twice: once at
    publish time against the raw, unresolved config (no `context.
    variables` exist yet, so a templated `open_time` is still literally
    the string `"{{business-settings.item.payload.open_time}}"` at that
    point - see `execute()`'s docstring for why runtime is the only place
    interpolation can happen) and once at runtime, against the output of
    `_interpolate_config` (by then a real resolved string, or the
    genuinely-invalid result of a bad/typo'd reference - see the module
    docstring). The "HH:MM" format validators below need to be lenient
    exactly at the first of those two checks, so a template-holding
    config isn't rejected before it's ever had a chance to resolve, while
    staying strict at the second (post-interpolation) so a broken
    reference is still caught, just later, with the real bad value in
    the error instead of a template marker."""
    return "{{" in value


class TimeWindow(BaseModel):
    """A named sub-window of the day (e.g. "morning") an author can offer
    a customer as a coarser choice than an exact time - purely a labelled
    `[start, end)` range within the business's overall open/close hours."""

    start: str = Field(description="24-hour 'HH:MM', e.g. '09:00'.")
    end: str = Field(description="24-hour 'HH:MM', e.g. '12:00'.")

    @field_validator("start", "end")
    @classmethod
    def _validate_hhmm(cls, value: str) -> str:
        if not _is_template(value):
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
    break_start: str | None = Field(
        default=None,
        description=(
            "24-hour 'HH:MM' a daily lunch/other break starts, e.g. '13:00'. Optional - a tenant "
            "with no break omits this (and break_end). Only affects 'is_open_now', not "
            "'time_of_day_passed' or 'time_windows' - see this module's docstring."
        ),
    )
    break_end: str | None = Field(
        default=None,
        description="24-hour 'HH:MM' the break configured by break_start ends, e.g. '14:00'.",
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
        if not _is_template(value):
            _parse_hhmm(value)
        return value

    @field_validator("break_start", "break_end")
    @classmethod
    def _validate_break_hhmm(cls, value: str | None) -> str | None:
        if value is not None and _is_template(value):
            return value
        # Both fields are optional (no break configured at all is the
        # common case) - only run the same "HH:MM" check `open_time`/
        # `close_time` use when a value is actually present.
        if value is not None:
            _parse_hhmm(value)
        return value

    @model_validator(mode="after")
    def _validate_break_pair(self) -> "BusinessHoursConfig":
        if (self.break_start is None) != (self.break_end is None):
            raise ValueError("break_start and break_end must both be set, or both omitted")
        return self


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


def _interpolate_config(raw_config: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    """Resolve `{{dot.path}}` templates in `raw_config` before Pydantic
    ever sees it, so a value like `"{{business-settings.item.payload.
    open_time}}"` lands as a real "HH:MM" string instead of failing
    `BusinessHoursConfig`'s validators as literal template-marker text.

    Deliberately touches an explicit, fixed set of fields
    (`open_time`/`close_time`/`break_start`/`break_end`, each
    `closed_weekdays` entry, each `time_windows[name].start`/`.end`)
    rather than recursively interpolating every string anywhere in
    `raw_config`. `day_reference`/`time_of_day` are also strings, but
    they're identifiers this node dispatches on (a `Literal` value, or a
    literal key into `time_windows`) rather than "HH:MM"-shaped data -
    same reasoning `connector.action`'s `params` and `records.upsert`'s
    `fields` already apply: templating is opt-in per field the node
    actually expects to hold interpolatable data, not assumed for every
    string an author could theoretically put in config. `interpolate` is
    a no-op on a plain string with no `{{...}}` marker, so a config
    written before this change (all literal "HH:MM" values) resolves to
    the exact same dict it started as.
    """
    config = dict(raw_config)

    for key in ("open_time", "close_time", "break_start", "break_end"):
        value = config.get(key)
        if isinstance(value, str):
            config[key] = interpolate(value, variables)

    closed_weekdays = config.get("closed_weekdays")
    if isinstance(closed_weekdays, list):
        config["closed_weekdays"] = [
            interpolate(day, variables) if isinstance(day, str) else day for day in closed_weekdays
        ]

    time_windows = config.get("time_windows")
    if isinstance(time_windows, dict):
        resolved_windows: dict[str, Any] = {}
        for name, window in time_windows.items():
            if isinstance(window, dict):
                resolved_window = dict(window)
                for edge in ("start", "end"):
                    edge_value = resolved_window.get(edge)
                    if isinstance(edge_value, str):
                        resolved_window[edge] = interpolate(edge_value, variables)
                resolved_windows[name] = resolved_window
            else:
                resolved_windows[name] = window
        config["time_windows"] = resolved_windows

    return config


def _in_break(config: "BusinessHoursConfig", now_time: time) -> bool:
    """Whether `now_time` falls inside the configured lunch/other break
    (`False` whenever no break is configured at all)."""
    if config.break_start is None or config.break_end is None:
        return False
    return _parse_hhmm(config.break_start) <= now_time < _parse_hhmm(config.break_end)


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
        config = BusinessHoursConfig.model_validate(_interpolate_config(context.config, context.variables))
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
            # Deliberately not break-aware: this answers "has the named
            # window's own end time already gone by", which the break
            # never changes (a window either already ended or it hasn't -
            # the break doesn't move its `end`). The break's only job is
            # gating `is_open_now` below; see this module's docstring.

        is_open_now = (
            today.strftime("%A").lower() not in closed_weekdays
            and _parse_hhmm(config.open_time) <= now.time() < _parse_hhmm(config.close_time)
            and not _in_break(config, now.time())
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
