"""Appointment reminder poller — third serverless-substitute poll, sibling
to `outbox_poller.py`/`schedule_poller.py`, invoked from the same
`/api/v1/internal/scheduled-tasks` Vercel Cron route (see
`internal_router.py`).

Why this isn't just another `WorkflowSchedule` row: that mechanism (see
`schedule_poller.py`) fires a broadcast at one fixed clock time per row
and resolves its recipient list via `ModuleRecipientSource.filters` -
exact-match equality filters only, with no way to express "any
appointment whose date/time falls within the next 2 hours from right
now", which is an inherently per-record relative-time condition, not a
fixed-time or exact-match one. This is a small, purpose-built poller
instead, following the exact same cross-tenant/RLS-context shape
`schedule_poller.poll_once` already establishes.

Recipient resolution: an `appointment` object record's `customer_id` FK
resolves to a `Customer` row, whose `external_ref` IS the Instagram-scoped
sender id (`instagram.find_or_create_customer` keys off exactly that) -
no new field needed there.

Meta's 24-hour customer-messaging window: confirmed via live research this
session that Instagram Messaging API supports none of Messenger's
"send outside the window" tags except `HUMAN_AGENT` (semantically for a
human agent's reply to an existing inquiry, and Instagram's adapter here
doesn't even implement tag support) - so this poller checks the
customer's `Conversation.last_message_at` for this connector instance and
skips (never sends untagged) if it's been more than 24 hours since their
last real message, logging the skip rather than risking a policy
violation or a silent Meta-side rejection. In practice this should rarely
trigger: this clinic's direct-calendar bookings are only ever for today
or tomorrow, so the gap between "customer messages to book" and "2 hours
before the appointment" is almost always well inside 24 hours.

`reminder_sent_at` (a plain ISO-datetime string, added as a TEXT custom
field on the `appointment` object type - there's no DATETIME `FieldType`,
only DATE, so TEXT is the pragmatic choice, same reasoning `preferred_time`/
`time_slot` already being TEXT reflects) marks a reminder as sent, so a
15-minute poll interval doesn't double-send inside the ~2-hour window.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fusionflow.db.session import async_session_factory, set_tenant_context
from fusionflow.modules.business_objects import service as bo_service
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import registry as connector_registry
from fusionflow.modules.connectors.models import ConnectorState
from fusionflow.modules.customers import service as customers_service
from fusionflow.modules.inbox.models import Conversation
from fusionflow.modules.tenancy.models import Business

logger = logging.getLogger(__name__)

_REMINDER_WINDOW = timedelta(hours=2)
_REMINDER_LOOKAHEAD_SLACK = timedelta(minutes=20)  # covers the poll interval so a due appointment isn't missed between passes.
_MAX_MESSAGE_AGE = timedelta(hours=24)
_TIME_LABEL_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)", re.IGNORECASE)
_IST = ZoneInfo("Asia/Kolkata")


def _parse_slot_start(appointment_date: str, time_slot: str) -> datetime | None:
    """`time_slot` is a display label like '10:00 AM - 10:30 AM' - pulls the
    start time out of it rather than requiring a new raw-time field on the
    appointment type (deliberately not touching the live Faheem booking
    graph's own upsert-appointment-* nodes for this - other agents are
    editing that exact area concurrently this session)."""
    match = _TIME_LABEL_RE.search(time_slot or "")
    if not match:
        return None
    hour, minute, meridiem = int(match.group(1)), int(match.group(2)), match.group(3).upper()
    if meridiem == "PM" and hour != 12:
        hour += 12
    if meridiem == "AM" and hour == 12:
        hour = 0
    try:
        d = date.fromisoformat(appointment_date)
    except ValueError:
        return None
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=_IST)


async def poll_once(session_factory: async_sessionmaker[AsyncSession] = async_session_factory) -> int:
    """One pass over every tenant. Returns the number of reminders sent."""
    async with session_factory() as session:
        tenant_ids = (await session.execute(select(Business.id))).scalars().all()

    sent = 0
    for tenant_id in tenant_ids:
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            sent += await _process_tenant_reminders(session, tenant_id)
    return sent


async def _process_tenant_reminders(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    object_type = await bo_service.get_object_type_by_key(session, tenant_id=tenant_id, key="appointment")
    if object_type is None:
        return 0

    records = await bo_service.list_records(session, tenant_id=tenant_id, object_type_id=object_type.id)
    now = datetime.now(_IST)
    due = []
    for record in records:
        payload = record.payload
        if payload.get("status") != "confirmed":
            continue
        if payload.get("reminder_sent_at"):
            continue
        appointment_date = payload.get("appointment_date")
        time_slot = payload.get("time_slot")
        if not appointment_date or not time_slot:
            continue
        slot_start = _parse_slot_start(appointment_date, time_slot)
        if slot_start is None:
            continue
        window_start = slot_start - _REMINDER_WINDOW - _REMINDER_LOOKAHEAD_SLACK
        window_end = slot_start - _REMINDER_WINDOW
        if window_start <= now <= window_end:
            due.append((record, slot_start))

    if not due:
        return 0

    instances = await connector_service.list_instances(session, tenant_id)
    ig_instance = next(
        (i for i in instances if i.connector_type.key == "instagram" and i.state == ConnectorState.CONNECTED),
        None,
    )
    if ig_instance is None:
        logger.warning("[appointment_reminders] tenant %s has due reminders but no connected instagram instance", tenant_id)
        return 0
    adapter = connector_registry.get_or_none("instagram")
    if adapter is None:
        return 0

    sent = 0
    for record, slot_start in due:
        if record.customer_id is None:
            continue
        customer = await customers_service.get_customer(session, tenant_id=tenant_id, customer_id=record.customer_id)
        if customer is None or not customer.external_ref:
            continue

        conversation = (
            await session.execute(
                select(Conversation).where(
                    Conversation.tenant_id == tenant_id,
                    Conversation.connector_instance_id == ig_instance.id,
                    Conversation.external_contact_id == customer.external_ref,
                )
            )
        ).scalar_one_or_none()
        if conversation is None or conversation.last_message_at is None:
            continue
        message_age = datetime.now(timezone.utc) - conversation.last_message_at
        if message_age > _MAX_MESSAGE_AGE:
            logger.info(
                "[appointment_reminders] skipping reminder for appointment %s - last message from customer "
                "was %s ago, outside Instagram's 24h messaging window and no compliant tag available",
                record.id,
                message_age,
            )
            continue

        payload = record.payload
        mode_line = (
            f"Join via Google Meet: {payload['meet_link']}"
            if payload.get("appointment_mode") == "online" and payload.get("meet_link")
            else "See you at the clinic!"
        )
        text = (
            f"⏰ Reminder: your consultation with Dr. Faheem is in about 2 hours, at {payload.get('time_slot')}.\n"
            f"{mode_line}"
        )

        try:
            await adapter.perform_action(
                action="send_direct_message",
                params={"recipient_id": customer.external_ref, "text": text},
                instance=ig_instance,
                session=session,
            )
        except Exception:
            logger.exception("[appointment_reminders] failed to send reminder for appointment %s", record.id)
            continue

        field_defs = await bo_service.list_field_definitions(session, tenant_id=tenant_id, object_type_id=object_type.id)
        await bo_service.update_record(
            session,
            record,
            field_defs=field_defs,
            payload={"reminder_sent_at": datetime.now(timezone.utc).isoformat()},
        )
        await session.commit()
        sent += 1

    return sent
