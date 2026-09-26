"""`instagram.ask_period_choice` — sends the "Morning / Afternoon /
Evening" period picker, but only for periods whose end time hasn't
already passed relative to right now (in `timezone`).

Without this, asking "which time of day?" on a same-day direct booking
could offer a period that's already entirely in the past (e.g. showing
"Afternoon" at 6pm when afternoon ends at 4pm) - the customer would tap
it, `instagram.ask_calendar_slot` would correctly find zero real slots
left in that window, and they'd see "no slots available" even though
Evening genuinely still has openings. This node moves that same "has
this window already ended" check one step earlier, so a customer is
simply never offered an option that could only ever dead-end.

Each period's own label/payload stays exactly what the graph already
sends today (e.g. `"DIRECT_ORTHO_TODAY_AFTERNOON"`) - this node changes
*which* of the 3 periods get offered, never the payload shape, so every
existing postback-routing entry downstream needs no changes at all.

For a future date (e.g. "tomorrow"), every period's end time is always
still ahead of "now" - this node is safe to use for that case too, it
just never ends up filtering anything out.
"""

from __future__ import annotations

import uuid
from datetime import datetime
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

_MAX_PERIODS = 3


class PeriodOption(BaseModel):
    label: str = Field(min_length=1, description="Button title, e.g. 'Afternoon'.")
    payload: str = Field(min_length=1, description="Postback payload, e.g. 'DIRECT_ORTHO_TODAY_AFTERNOON' - unchanged from today's static buttons.")
    end_time: str = Field(min_length=1, description="Templated 'HH:MM', e.g. '{{business-settings-pb.item.payload.afternoon_end}}'.")


class AskPeriodChoiceConfig(BaseModel):
    instagram_connector_instance_id: str = Field(min_length=1)
    recipient_id: str = Field(min_length=1, description="Usually '{{trigger.from}}'.")
    text: str = Field(min_length=1, json_schema_extra={"format": "textarea"})
    date: str = Field(min_length=1, description="Templated 'YYYY-MM-DD' - the date these periods are offered for.")
    timezone: str = Field(default="Asia/Kolkata")
    periods: list[PeriodOption] = Field(min_length=1, max_length=_MAX_PERIODS)

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


_OUTPUT_SCHEMA = {"type": "object", "properties": {"sent_count": {"type": "integer"}}}


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour_str, _, minute_str = value.partition(":")
    return int(hour_str), int(minute_str)


class AskPeriodChoiceExecutor(NodeExecutor):
    node_type = "instagram.ask_period_choice"
    kind = "action"
    category = "Messages"
    subcategory = "Ask"
    palette_group = "Talk to Customer"
    icon = "clock"
    label = "Ask Which Period (Instagram, elapsed-aware)"
    description = "Sends the morning/afternoon/evening picker, skipping any period whose window has already ended today."
    config_model = AskPeriodChoiceConfig
    output_schema = _OUTPUT_SCHEMA
    required_connector_type_key = "instagram"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = AskPeriodChoiceConfig.model_validate(context.config)
        recipient_id = interpolate(config.recipient_id, context.variables)
        text = interpolate(config.text, context.variables)
        date_str = interpolate(config.date, context.variables)
        tz_name = interpolate(config.timezone, context.variables)

        try:
            instance_id = uuid.UUID(config.instagram_connector_instance_id)
        except ValueError:
            return Failure(f"connector_instance_id {config.instagram_connector_instance_id!r} is not a valid UUID")
        instance = await connector_service.get_instance(context.session, tenant_id=context.tenant_id, instance_id=instance_id)
        if instance is None:
            return Failure(f"connector instance {instance_id} not found for this tenant")
        adapter = connector_registry.get_or_none(instance.connector_type.key)
        if adapter is None:
            return Failure("no adapter registered for the resolved connector instance")

        try:
            tz = ZoneInfo(tz_name)
            year, month, day = (int(p) for p in date_str.split("-"))
        except (ValueError, ZoneInfoNotFoundError) as exc:
            return Failure(f"could not resolve date: {exc}")

        now = datetime.now(tz)
        buttons = []
        for period in config.periods:
            end_time_str = interpolate(period.end_time, context.variables)
            try:
                end_h, end_m = _parse_hhmm(end_time_str)
                period_end = datetime(year, month, day, end_h, end_m, tzinfo=tz)
            except ValueError:
                continue
            if period_end > now:
                buttons.append({"type": "postback", "title": period.label, "payload": period.payload})

        if not buttons:
            return Success(output={"sent_count": 0})

        try:
            await adapter.perform_action(
                action="send_button_template",
                params={"recipient_id": recipient_id, "text": text, "buttons": buttons},
                instance=instance,
                session=context.session,
            )
        except NotImplementedError as exc:
            return Failure(str(exc))

        return Success(output={"sent_count": len(buttons)})


node_executor_registry.register(AskPeriodChoiceExecutor())
