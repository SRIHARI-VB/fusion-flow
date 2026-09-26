"""Post-visit feedback poller — a third, independent poller alongside
`outbox_poller.py`/`schedule_poller.py`, same `JobQueue`-handler shape and
same cross-tenant iteration pattern (see either of those two for the
"provision but skip in dev" rationale this repeats).

Once a day (default), for every tenant, finds `appointment` custom-object
records with `status: "confirmed"` whose `appointment_date` was
YESTERDAY (in Asia/Kolkata - not yet tenant-configurable, matching this
whole feature area's existing "Faheem-specific default, generalize later"
posture) and that have never had a feedback ask sent (`feedback_requested_at`
unset), and sends a short feedback prompt to the customer via whichever
connected `instagram` instance the tenant has.

**Real, load-bearing platform constraint - read before changing this
file**: Meta only allows an app to freely message a user within 24 hours
of that user's last message to the business account. There IS a tag
that bypasses this (`HUMAN_AGENT`), but Meta's own policy explicitly
prohibits applying it to an automated/bot-sent message - it exists for a
live human agent taking over a conversation, not this kind of scheduled
job. The transactional tags that used to cover this case
(`CONFIRMED_EVENT_UPDATE`/`ACCOUNT_UPDATE`/`POST_PURCHASE_UPDATE`) were
deprecated by Meta as of 2026-04-27 (now return error code 100). There is
therefore no compliant way for *this* poller to guarantee delivery a full
day after a visit - it sends a perfectly ordinary, untagged message
(exactly what a compliant app is supposed to do), and Meta will reject it
whenever that customer's own last message to the account is more than 24h
old (the overwhelmingly common case for a next-day ask). That rejection
is caught and logged here, not treated as a poller failure - some
customers who happen to re-engage naturally around visit time will get a
real prompt; the rest simply won't, and that's a genuine Instagram
platform limitation, not a bug in this file. The only way to reach
100% of customers would be to weave the ask into the *next* message the
customer sends the bot instead (a reply, always within-window by
definition) - that would mean touching the live Faheem conversational
workflow's own graph, deliberately out of scope for this change (see the
task this was built under). This poller still does the useful, safe
part on its own: it marks exactly who is due, via `feedback_requested_at`,
so a future reply-triggered version has the bookkeeping already done.

Startup wiring (add to `main.py`'s `lifespan`, alongside the other two
pollers):

    register_feedback_poller(app.state.jobs)
    await start_feedback_poller(app.state.jobs)
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fusionflow.db.session import async_session_factory, set_tenant_context
from fusionflow.modules.business_objects import service as bo_service
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import registry as connector_registry
from fusionflow.modules.connectors.models import ConnectorState
from fusionflow.modules.customers import service as customers_service
from fusionflow.modules.tenancy.models import Business

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fusionflow.core.jobs import JobQueue

logger = logging.getLogger(__name__)

JOB_NAME = "workflows.feedback_poll"
DEFAULT_INTERVAL_SECONDS = 3600.0  # once an hour is plenty for a "was it yesterday" check
_TZ = ZoneInfo("Asia/Kolkata")
_APPOINTMENT_TYPE_KEY = "appointment"
_FEEDBACK_TEXT = (
    "We hope your visit went well! We'd love a quick word on how it went - "
    "just reply here and let us know."
)


def _yesterday_date_str() -> str:
    return (datetime.now(_TZ) - timedelta(days=1)).date().isoformat()


async def poll_once(
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
) -> int:
    """One pass over every tenant. Returns the number of feedback asks attempted."""
    async with session_factory() as session:
        tenant_ids = (await session.execute(select(Business.id))).scalars().all()

    attempted = 0
    for tenant_id in tenant_ids:
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            attempted += await _process_tenant(session, tenant_id)
    return attempted


async def _process_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    object_type = await bo_service.get_object_type_by_key(session, tenant_id=tenant_id, key=_APPOINTMENT_TYPE_KEY)
    if object_type is None:
        return 0

    field_defs = await bo_service.list_field_definitions(session, tenant_id=tenant_id, object_type_id=object_type.id)
    records = await bo_service.list_records(session, tenant_id=tenant_id, object_type_id=object_type.id)

    yesterday = _yesterday_date_str()
    due = [
        r
        for r in records
        if r.payload.get("status") == "confirmed"
        and r.payload.get("appointment_date") == yesterday
        and not r.payload.get("feedback_requested_at")
    ]
    if not due:
        return 0

    instances = await connector_service.list_instances(session, tenant_id)
    ig_instance = next(
        (i for i in instances if i.connector_type.key == "instagram" and i.state == ConnectorState.CONNECTED),
        None,
    )

    attempted = 0
    for record in due:
        await _ask_for_feedback(session, tenant_id, record, field_defs, ig_instance)
        attempted += 1

    await session.commit()
    return attempted


async def _ask_for_feedback(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    record: Any,
    field_defs: list[Any],
    ig_instance: Any | None,
) -> None:
    sent_ok = False
    if ig_instance is not None and record.customer_id is not None:
        customer = await customers_service.get_customer(session, tenant_id, record.customer_id)
        if customer is not None and customer.external_ref:
            adapter = connector_registry.get_or_none(ig_instance.connector_type.key)
            if adapter is not None:
                try:
                    await adapter.perform_action(
                        action="send_direct_message",
                        params={"recipient_id": customer.external_ref, "text": _FEEDBACK_TEXT},
                        instance=ig_instance,
                        session=session,
                    )
                    sent_ok = True
                except Exception as exc:  # noqa: BLE001 - a Meta rejection (24h window, etc.) is expected, not a bug
                    logger.info(
                        "feedback_poller: could not message customer %s for appointment %s (expected if "
                        "outside Meta's 24h window - see module docstring): %s",
                        record.customer_id,
                        record.id,
                        exc,
                    )

    # Marked as asked either way - this is a "once, best-effort" ask, not a
    # retry-until-delivered one; see module docstring for why retrying a
    # rejected send would just be repeating a call Meta will keep declining.
    await bo_service.update_record(
        session,
        record,
        field_defs=field_defs,
        payload={"feedback_requested_at": datetime.now(timezone.utc).isoformat()},
    )
    logger.info(
        "feedback_poller: appointment %s marked feedback_requested_at (message %s)",
        record.id,
        "sent" if sent_ok else "not delivered",
    )


async def _poll_forever_job(
    jobs: "JobQueue",
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    await poll_once(session_factory)
    await asyncio.sleep(interval_seconds)
    await jobs.enqueue(
        JOB_NAME, jobs=jobs, session_factory=session_factory, interval_seconds=interval_seconds
    )


def register_feedback_poller(jobs: "JobQueue") -> None:
    """Register the poller's job handler. Call exactly once per process."""
    jobs.register_handler(JOB_NAME, _poll_forever_job)


async def start_feedback_poller(
    jobs: "JobQueue",
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Kick off the recurring poll loop. Call once at startup, after
    `register_feedback_poller`."""
    await jobs.enqueue(
        JOB_NAME, jobs=jobs, session_factory=session_factory, interval_seconds=interval_seconds
    )
