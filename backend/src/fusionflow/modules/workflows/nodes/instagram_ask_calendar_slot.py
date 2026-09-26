"""`instagram.ask_calendar_slot` — computes real available time slots
within a period (e.g. "morning") on a given date, by checking the
tenant's connected Google Calendar's actual busy events, and sends up to
3 of them as Instagram postback buttons.

Combines "compute the slots" and "send them" into one node rather than a
separate compute-then-render pair, for the same reason
`instagram.ask_choice` does: the computed slot list is exactly the kind
of list-of-things `resolve_path`'s dict-only traversal can never expose to
a template (`{{node.slots.0.label}}` doesn't resolve), so nothing else in
this engine could actually turn a plain "here are the slots" output into
buttons without this node doing the rendering itself.

Each button's payload is `"SLOT:<start_iso>|<end_iso>"` (pipe, not colon,
as the inner separator - an ISO datetime string already contains colons
itself, e.g. `2026-09-26T10:00:00+05:30`, so colon-splitting the two
halves back apart would be ambiguous) - fully self-contained (no DB
lookup needed to resolve it later), parsed back apart by the paired
`calendar.parse_slot_choice` node.

More than 3 available slots in a period is a graph-authoring pattern
(chain two instances with offset=0,3, exactly like `instagram.ask_choice`
already established for services/products), not something this single
node paginates internally.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import registry as connector_registry
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate

_MAX_BUTTONS = 3
_MAX_TITLE_LENGTH = 20


class AskCalendarSlotConfig(BaseModel):
    instagram_connector_instance_id: str = Field(min_length=1, description="Instagram instance to send from.")
    calendar_connector_instance_id: str = Field(min_length=1, description="Google Calendar instance to check.")
    recipient_id: str = Field(min_length=1, description="Usually '{{trigger.from}}'.")
    text: str = Field(min_length=1, json_schema_extra={"format": "textarea"})
    date: str = Field(min_length=1, description="Templated 'YYYY-MM-DD', usually from schedule.is_direct_booking_day's .date output.")
    period_start: str = Field(min_length=1, description="Templated 'HH:MM', e.g. from business_settings.morning_start.")
    period_end: str = Field(min_length=1, description="Templated 'HH:MM'.")
    timezone: str = Field(default="Asia/Kolkata")
    slot_minutes: int = Field(default=30, ge=5, le=180)
    limit: int = Field(default=3, ge=1, le=_MAX_BUTTONS)
    offset: int = Field(default=0, ge=0)

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        if "{{" in value:
            return value
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown IANA timezone: {value!r}") from exc
        return value


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"sent_count": {"type": "integer"}, "has_more": {"type": "boolean"}},
}


def _format_12h(dt: datetime) -> str:
    """`"2:30 PM"`, no leading zero - `%-I` is a Unix-only strftime
    extension (works on this app's Linux/Vercel runtime, but raises
    `ValueError: Invalid format string` on Windows). `%I` + manual lstrip
    is portable - see calendar_parse_slot_choice.py's identical helper."""
    return dt.strftime("%I:%M %p").lstrip("0")


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour_str, _, minute_str = value.partition(":")
    return int(hour_str), int(minute_str)


async def _resolve_instance(context: ExecutionContext, instance_id_str: str):
    try:
        instance_id = uuid.UUID(instance_id_str)
    except ValueError:
        return Failure(f"connector_instance_id {instance_id_str!r} is not a valid UUID")
    instance = await connector_service.get_instance(context.session, tenant_id=context.tenant_id, instance_id=instance_id)
    if instance is None:
        return Failure(f"connector instance {instance_id} not found for this tenant")
    return instance


class AskCalendarSlotExecutor(NodeExecutor):
    node_type = "instagram.ask_calendar_slot"
    kind = "action"
    category = "Messages"
    subcategory = "Ask"
    palette_group = "Talk to Customer"
    icon = "calendar-clock"
    label = "Ask Customer to Pick a Calendar Slot (Instagram)"
    description = "Computes real available time slots from a connected Google Calendar and sends up to 3 as buttons."
    config_model = AskCalendarSlotConfig
    output_schema = _OUTPUT_SCHEMA
    required_connector_type_key = "instagram"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = AskCalendarSlotConfig.model_validate(context.config)
        recipient_id = interpolate(config.recipient_id, context.variables)
        text = interpolate(config.text, context.variables)
        date_str = interpolate(config.date, context.variables)
        period_start_str = interpolate(config.period_start, context.variables)
        period_end_str = interpolate(config.period_end, context.variables)
        tz_name = interpolate(config.timezone, context.variables)

        ig_instance = await _resolve_instance(context, config.instagram_connector_instance_id)
        if isinstance(ig_instance, Failure):
            return ig_instance
        cal_instance = await _resolve_instance(context, config.calendar_connector_instance_id)
        if isinstance(cal_instance, Failure):
            return cal_instance

        ig_adapter = connector_registry.get_or_none(ig_instance.connector_type.key)
        cal_adapter = connector_registry.get_or_none(cal_instance.connector_type.key)
        if ig_adapter is None or cal_adapter is None:
            return Failure("no adapter registered for one of the resolved connector instances")

        try:
            tz = ZoneInfo(tz_name)
            year, month, day = (int(p) for p in date_str.split("-"))
            start_h, start_m = _parse_hhmm(period_start_str)
            end_h, end_m = _parse_hhmm(period_end_str)
            period_start = datetime(year, month, day, start_h, start_m, tzinfo=tz)
            period_end = datetime(year, month, day, end_h, end_m, tzinfo=tz)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            return Failure(f"could not resolve date/period: {exc}")

        if period_end <= period_start:
            return Success(output={"sent_count": 0, "has_more": False})

        try:
            busy_result = await cal_adapter.perform_action(
                action="list_events",
                params={"time_min": period_start.isoformat(), "time_max": period_end.isoformat(), "max_results": 50},
                instance=cal_instance,
                session=context.session,
            )
        except NotImplementedError as exc:
            return Failure(str(exc))

        busy_periods: list[tuple[datetime, datetime]] = []
        for item in busy_result.get("items", []):
            item_start = item.get("start", {}).get("dateTime")
            item_end = item.get("end", {}).get("dateTime")
            if not item_start or not item_end:
                continue  # all-day event ("date" key, not "dateTime") - not a timed conflict, skip.
            try:
                busy_periods.append((datetime.fromisoformat(item_start), datetime.fromisoformat(item_end)))
            except ValueError:
                continue

        slot_delta = timedelta(minutes=config.slot_minutes)
        now = datetime.now(tz)
        candidates: list[tuple[datetime, datetime]] = []
        cursor = period_start
        while cursor + slot_delta <= period_end:
            slot_end = cursor + slot_delta
            if cursor > now and not any(cursor < b_end and slot_end > b_start for b_start, b_end in busy_periods):
                candidates.append((cursor, slot_end))
            cursor = slot_end

        window = candidates[config.offset : config.offset + config.limit]
        has_more = len(candidates) > config.offset + config.limit

        if not window:
            return Success(output={"sent_count": 0, "has_more": False})

        buttons = []
        for slot_start, slot_end in window:
            label = f"{_format_12h(slot_start)} - {_format_12h(slot_end)}"[:_MAX_TITLE_LENGTH]
            payload = f"SLOT:{slot_start.isoformat()}|{slot_end.isoformat()}"
            buttons.append({"type": "postback", "title": label, "payload": payload})

        try:
            await ig_adapter.perform_action(
                action="send_button_template",
                params={"recipient_id": recipient_id, "text": text, "buttons": buttons},
                instance=ig_instance,
                session=context.session,
            )
        except NotImplementedError as exc:
            return Failure(str(exc))

        return Success(output={"sent_count": len(buttons), "has_more": has_more})


node_executor_registry.register(AskCalendarSlotExecutor())
