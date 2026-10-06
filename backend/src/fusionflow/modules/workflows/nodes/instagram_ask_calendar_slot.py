"""`instagram.ask_calendar_slot` — computes real available time slots
within a period (e.g. "morning") on a given date, by checking the
tenant's connected Google Calendar's actual busy events, and sends the
available choices as button messages, with at most three buttons each.

Combines "compute the slots" and "send them" into one node rather than a
separate compute-then-render pair, for the same reason
`instagram.ask_choice` does: the computed slot list is exactly the kind
of list-of-things `resolve_path`'s dict-only traversal can never expose to
a template (`{{node.slots.0.label}}` doesn't resolve), so nothing else in
this engine could actually turn a plain "here are the slots" output into
buttons without this node doing the rendering itself.

Each button's payload is `"SLOT:<context>|<start_iso>|<end_iso>"` (pipe,
not colon, as the separator - an ISO datetime string already contains
colons itself, e.g. `2026-09-26T10:00:00+05:30`, so colon-splitting the
parts back apart would be ambiguous) - fully self-contained (no DB
lookup needed to resolve it later), parsed back apart by the paired
`calendar.parse_slot_choice` node. `context` is an opaque, caller-chosen
passthrough string (e.g. which of several parallel day/concern chains
led here) - this node never inspects it, it exists purely so a workflow
author can recover "what was this a slot for" once the tap that picked a
slot starts a brand-new run (postback taps always do in this engine) and
the original chain's variables are gone.

`limit` and `offset` select the slot window independently of the per-message
button cap. Up to 288 slots covers a full day at the minimum five minutes.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import ConnectorReconnectRequired, registry as connector_registry
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate

logger = logging.getLogger(__name__)

_MAX_OPTIONS = 288
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
    slot_minutes: str = Field(
        default="30",
        description=(
            "Templated int, usually '{{business-settings-pb.item.payload.appointment_slot_minutes}}' "
            "- the tenant's configurable appointment-slot-duration setting (10-120 min). A plain "
            "literal like '30' also works."
        ),
    )
    limit: int = Field(default=13, ge=1, le=_MAX_OPTIONS)
    offset: int = Field(default=0, ge=0)
    calendar_unavailable_text: str = Field(
        default="Sorry, online appointment booking is temporarily unavailable. "
        "Please contact the clinic directly to arrange your visit.",
        min_length=1,
        json_schema_extra={"format": "textarea"},
    )
    context: str = Field(
        default="",
        description=(
            "Templated, opaque passthrough embedded in each button's payload and echoed back by "
            "calendar.parse_slot_choice - use it to carry state (e.g. which concern/day chain this "
            "was) across the run boundary a postback tap always creates. Must not contain '|'."
        ),
    )

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
    description = "Computes real available time slots from a connected Google Calendar and sends the choices as button messages in groups of three."
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
        context_str = interpolate(config.context, context.variables).replace("|", "")

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

        slot_minutes_str = interpolate(config.slot_minutes, context.variables)
        try:
            slot_minutes = int(float(slot_minutes_str))
        except ValueError:
            return Failure(f"slot_minutes resolved to a non-numeric value: {slot_minutes_str!r}")
        slot_minutes = max(5, min(180, slot_minutes))

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
                params={"time_min": period_start.isoformat(), "time_max": period_end.isoformat(),
                        "max_results": 50, "require_live": True},
                instance=cal_instance,
                session=context.session,
            )
        except ConnectorReconnectRequired as exc:
            # Stop here: failed authorization is not an empty calendar and
            # must never flow into the downstream "no slots"/booking branch.
            try:
                await ig_adapter.perform_action(
                    action="send_direct_message",
                    params={"recipient_id": recipient_id,
                            "text": interpolate(config.calendar_unavailable_text, context.variables)},
                    instance=ig_instance,
                    session=context.session,
                )
            except Exception:  # A failed notice must not retry the revoked grant.
                logger.exception("Could not send the calendar-unavailable notice for node %s", context.node_id)
            return Failure(str(exc))
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

        slot_delta = timedelta(minutes=slot_minutes)
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

        replies = []
        for slot_start, slot_end in window:
            label = f"{_format_12h(slot_start)} - {_format_12h(slot_end)}"[:_MAX_TITLE_LENGTH]
            payload = f"SLOT:{context_str}|{slot_start.isoformat()}|{slot_end.isoformat()}"
            replies.append({"title": label, "payload": payload})

        try:
            await ig_adapter.perform_action(
                action="send_button_template",
                params={"recipient_id": recipient_id, "text": text, "buttons": replies},
                instance=ig_instance,
                session=context.session,
            )
        except NotImplementedError as exc:
            return Failure(str(exc))

        return Success(output={"sent_count": len(replies), "has_more": has_more})


node_executor_registry.register(AskCalendarSlotExecutor())
