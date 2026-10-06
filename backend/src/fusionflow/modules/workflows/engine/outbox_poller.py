"""Outbox poller — the other half of the transactional-outbox pattern.

Reads unprocessed `workflow_trigger_inbox` rows, matches each against the
denormalized `workflow_triggers` index, starts a `WorkflowRun` per match,
and calls `run_loop.execute_run`. Written only against the `JobQueue`
protocol from `core/jobs.py` (never `asyncio.create_task`/Celery directly)
per the plan's "provision but skip in dev" rule — see `register_handler`
usage below.

Startup wiring lives in `main.py`'s `lifespan`, right after
`app.state.jobs = get_job_queue(settings)`:

    register_outbox_poller(app.state.jobs)
    await start_outbox_poller(app.state.jobs)

`register_outbox_poller` is idempotent-unsafe by design (it calls
`JobQueue.register_handler`, which raises on a duplicate name) so it must
be called exactly once per process, at startup — exactly where the cache/
job backend selection already happens.

Recurring execution out of `JobQueue.enqueue`'s only primitive ("run this
once, soon"): `_poll_forever_job` polls once, sleeps `interval_seconds`,
then re-enqueues itself. `InProcessAsyncQueue`'s bounded retry-on-exception
wraps each pass, so one failing pass doesn't kill the polling loop
outright — only that pass's attempt is retried/logged.

Dispatch is serialized per event and tenant using a transaction advisory lock, so
concurrent workers cannot process a reply ahead of a queued reset. Inbox
rows are also locked against double processing. Each event commits
independently, and dispatch failures are quarantined instead of replayed.
`poll_once` visits tenants that actually have unprocessed inbox rows (one indexed
query) instead of scanning every tenant in `businesses` every cycle.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fusionflow.db.session import async_session_factory, set_tenant_context
from fusionflow.modules.inbox import service as inbox_service
from fusionflow.modules.tenancy.models import Business
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine import event_bus
from fusionflow.modules.workflows.engine.conversation_reset import INSTAGRAM_EVENTS, prepare_instagram_event
from fusionflow.modules.workflows.engine.appointment_reset import (
    CALENDAR_CANCEL_EVENT, defer_calendar_cancellation, dispatch_calendar_cancellation,
)
from fusionflow.modules.workflows.engine.run_loop import DELAY_CORRELATION_KEY, RunLoopError, execute_run, resume_run
from fusionflow.modules.workflows.models import (
    RunStatus,
    Workflow,
    WorkflowRun,
    WorkflowTrigger,
    WorkflowTriggerInbox,
    WorkflowVersion,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fusionflow.core.jobs import JobQueue

logger = logging.getLogger(__name__)

JOB_NAME = "workflows.outbox_poll"
DEFAULT_INTERVAL_SECONDS = 2.0

# Trigger types shaped like a DM (a `from` field that resolves to a
# Unified Inbox `Conversation`) - the only ones the "human handoff" pause
# gate below applies to. A comment/mention/reaction/etc. trigger has no
# corresponding `Conversation`, so the gate is skipped for those entirely
# rather than doing a lookup that could never match.
_CONVERSATIONAL_TRIGGER_TYPES = {
    "whatsapp.message_received",
    "instagram.message_received",
    "telegram.message_received",
    "facebook.message_received",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _lock_tenant_dispatch(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    # Lock BEFORE selecting inbox rows. SKIP LOCKED alone lets a second
    # worker overtake /clear with a newer message. Block rather than skip:
    # on serverless there may be no later poll to process that newer row.
    key = int.from_bytes(hashlib.sha256(f"workflow-dispatch:{tenant_id}".encode()).digest()[:8],
                         byteorder="big", signed=True)
    await session.execute(select(func.pg_advisory_xact_lock(key)))


async def poll_once(
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
) -> int:
    """One pass over every tenant that actually has unprocessed inbox rows.
    Returns the number of inbox rows processed (matched or not).

    The candidate-tenant lookup itself still needs a tenant context to
    legally read `workflow_trigger_inbox` under RLS (see `db/session.py`'s
    `SET LOCAL` docstring / plan Risk #2), so it goes through `businesses`
    (a platform table with no RLS policy) exactly as before — the
    optimization is querying each candidate' inbox once, cheaply, from
    inside that same scoped connection rather than unconditionally running
    the full dispatch path for every tenant regardless of whether it has
    any pending work.
    """
    async with session_factory() as session:
        tenant_ids = (await session.execute(select(Business.id))).scalars().all()

    processed = 0
    for tenant_id in tenant_ids:
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            has_pending = (
                await session.execute(
                    select(WorkflowTriggerInbox.id)
                    .where(
                        WorkflowTriggerInbox.tenant_id == tenant_id,
                        WorkflowTriggerInbox.processed_at.is_(None),
                        or_(WorkflowTriggerInbox.available_at.is_(None), WorkflowTriggerInbox.available_at <= _now()),
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if has_pending is None:
                continue
            processed += await _process_tenant_inbox(session, tenant_id)

    for tenant_id in tenant_ids:
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            await _resume_due_delays(session, tenant_id)
            await _expire_stale_waits(session, tenant_id)

    return processed


async def _resume_due_delays(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """`flow.delay`'s timer firing - the opposite of `_expire_stale_waits`
    just below: identified by the same sentinel `DELAY_CORRELATION_KEY`
    every delay-wait uses (see `run_loop.py`'s module docstring), these
    runs are meant to auto-CONTINUE once their (short, node-configured)
    expiry elapses, not fail. Must run before `_expire_stale_waits` in the
    same pass so a delay wait is never mistaken for a stale reply-wait and
    force-failed instead of resumed."""
    await _lock_tenant_dispatch(session, tenant_id)
    due_runs = (
        await session.execute(
            select(WorkflowRun).where(
                WorkflowRun.tenant_id == tenant_id,
                WorkflowRun.status == RunStatus.WAITING,
                WorkflowRun.waiting_correlation_key == DELAY_CORRELATION_KEY,
                WorkflowRun.waiting_expires_at < _now(),
            )
        )
    ).scalars().all()
    if not due_runs:
        return
    for run in due_runs:
        version = await session.get(WorkflowVersion, run.workflow_version_id)
        if version is None:
            logger.warning("workflow run %s (flow.delay) references missing workflow version", run.id)
            continue
        graph = WorkflowGraph.from_json(version.compiled_graph or version.graph)
        try:
            await resume_run(session, run, graph, reply_payload={})
        except RunLoopError as exc:
            run.status = RunStatus.FAILED
            run.completed_at = _now()
            logger.warning("workflow run %s could not resume from flow.delay: %s", run.id, exc)
    await session.commit()


async def _expire_stale_waits(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Force-fail any run that has been `WAITING` past its
    `waiting_expires_at` (fixed 24h from suspend, see run_loop.py's
    `_persist_suspension`) - a customer who never replies must not leave a
    run paused forever. No configurable "on timeout" branch in this v1
    (see Phase 8's plan section) - a plain, clearly-logged force-fail.
    Waiting runs are rare compared to inbox rows, so a straightforward
    loop (not the `FOR UPDATE SKIP LOCKED` batching the inbox path uses)
    is fine here.

    Excludes `flow.delay` waits (`DELAY_CORRELATION_KEY`) - those are
    handled by `_resume_due_delays` above, which runs first in the same
    pass; this query would otherwise force-fail a delay the instant it
    elapses instead of letting it resume."""
    await _lock_tenant_dispatch(session, tenant_id)
    stale_runs = (
        await session.execute(
            select(WorkflowRun).where(
                WorkflowRun.tenant_id == tenant_id,
                WorkflowRun.status == RunStatus.WAITING,
                WorkflowRun.waiting_expires_at < _now(),
                WorkflowRun.waiting_correlation_key != DELAY_CORRELATION_KEY,
            )
        )
    ).scalars().all()
    if not stale_runs:
        return
    for run in stale_runs:
        run.status = RunStatus.FAILED
        run.completed_at = _now()
        logger.warning(
            "workflow run %s timed out waiting for a reply after 24h (node=%s, correlation_key=%s)",
            run.id,
            run.waiting_node_id,
            run.waiting_correlation_key,
        )
    await session.commit()


async def _process_tenant_inbox(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    processed = 0
    while True:
        # Each event commits independently. Re-establish RLS and the ordering
        # lock after every commit; another worker may drain the next event.
        await set_tenant_context(session, tenant_id)
        await _lock_tenant_dispatch(session, tenant_id)
        inbox_row = (await session.execute(
            select(WorkflowTriggerInbox).where(
                WorkflowTriggerInbox.tenant_id == tenant_id,
                WorkflowTriggerInbox.processed_at.is_(None),
                or_(WorkflowTriggerInbox.available_at.is_(None), WorkflowTriggerInbox.available_at <= _now()),
            ).order_by(WorkflowTriggerInbox.created_at, WorkflowTriggerInbox.id)
            .limit(1).with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if inbox_row is None:
            await session.commit()  # Release the dispatch lock even on an empty queue.
            return processed

        inbox_id = inbox_row.id
        try:
            # Flush INSIDE the savepoint: constraint errors can surface only
            # when the last node's pending WAITING transition reaches Postgres.
            async with session.begin_nested():
                await _dispatch_inbox_row(session, tenant_id, inbox_row)
                await session.flush()
        except Exception as exc:
            # Provider effects cannot be rolled back. Preserve the failed
            # event for investigation, but do not send its question again on
            # every webhook or stop unrelated conversations behind it.
            logger.exception("workflow inbox row %s failed", inbox_id)
            inbox_row = await session.get(WorkflowTriggerInbox, inbox_id, populate_existing=True)
            sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
            inbox_row.processing_error = (
                f"{type(exc).__name__}{f' ({sqlstate})' if sqlstate else ''}; "
                "automatic replay disabled; review required"
            )
            if inbox_row.event_type == CALENDAR_CANCEL_EVENT:
                defer_calendar_cancellation(inbox_row, exc)
            else:
                inbox_row.available_at = None
        if inbox_row.event_type != CALENDAR_CANCEL_EVENT or inbox_row.available_at is None:
            inbox_row.processed_at = _now()
        await session.commit()
        processed += 1


async def _dispatch_inbox_row(
    session: AsyncSession, tenant_id: uuid.UUID, inbox_row: WorkflowTriggerInbox,
) -> None:
    if inbox_row.event_type == CALENDAR_CANCEL_EVENT:
        await dispatch_calendar_cancellation(session, inbox_row)
        return
    reset = None
    if inbox_row.event_type in INSTAGRAM_EVENTS:
        reset = await prepare_instagram_event(session, inbox_row)
        if reset.handled:
            return
        if (inbox_row.event_type == "instagram.message_received"
                and inbox_row.connector_instance_id is not None and inbox_row.payload.get("from")):
            pending_run = await event_bus.find_pending_wait(
                session, tenant_id=tenant_id,
                connector_instance_id=inbox_row.connector_instance_id,
                correlation_key=inbox_row.payload["from"],
            )
            if pending_run is not None:
                await _resume_waiting_run(session, pending_run, inbox_row.payload)
                return
    if inbox_row.event_type == "workflow.resume":
        await _resume_run_for_inbox_row(session, inbox_row)
        return

    matching = (
        await session.execute(
            select(WorkflowTrigger).where(
                WorkflowTrigger.tenant_id == tenant_id,
                WorkflowTrigger.trigger_type == inbox_row.event_type,
            )
        )
    ).scalars().all()

    if inbox_row.connector_instance_id is not None:
        matching = [
            t
            for t in matching
            if t.connector_instance_id is None
            or t.connector_instance_id == inbox_row.connector_instance_id
        ]

    if (
        inbox_row.event_type in _CONVERSATIONAL_TRIGGER_TYPES
        and inbox_row.connector_instance_id is not None
        and isinstance(inbox_row.payload, dict)
        and inbox_row.payload.get("from")
        and await inbox_service.is_automation_paused(
            session,
            tenant_id=tenant_id,
            connector_instance_id=inbox_row.connector_instance_id,
            external_contact_id=inbox_row.payload["from"],
        )
    ):
        # Human handoff (`inbox.pause_automation`) is in effect for
        # this conversation - skip starting any run for it, but still
        # mark the row processed (same "no match" outcome as a
        # keyword condition that didn't fire, not an error).
        return

    for trigger in matching:
        run = await _start_run_for_trigger(session, trigger, inbox_row)
        if (reset is not None and reset.conversation is not None and run is not None
                and run.status in {RunStatus.COMPLETED, RunStatus.WAITING}):
            reset.conversation.flow_reset_pending = False


async def _resume_run_for_inbox_row(session: AsyncSession, inbox_row: WorkflowTriggerInbox) -> None:
    """Handle a `workflow.resume`-typed inbox row (written by
    `event_bus.publish_resume_event`): re-verify the referenced run is
    still `WAITING` (defensive, in case of a race - e.g. it already timed
    out via `poll_once`'s expiry sweep) and, if so, continue it via
    `run_loop.resume_run` instead of starting a new run."""
    run_id = uuid.UUID(inbox_row.payload["run_id"])
    run = await session.get(WorkflowRun, run_id)
    if run is None or run.status != RunStatus.WAITING:
        logger.info(
            "workflow.resume inbox row %s references run %s which is no longer waiting - skipping",
            inbox_row.id,
            run_id,
        )
        return

    await _resume_waiting_run(session, run, inbox_row.payload["reply"])


async def _resume_waiting_run(session: AsyncSession, run: WorkflowRun, reply_payload: dict) -> None:
    version = await session.get(WorkflowVersion, run.workflow_version_id)
    if version is None:
        logger.warning("workflow run %s references missing workflow version %s", run.id, run.workflow_version_id)
        return

    graph = WorkflowGraph.from_json(version.compiled_graph or version.graph)
    try:
        await resume_run(session, run, graph, reply_payload=reply_payload)
    except RunLoopError as exc:
        run.status = RunStatus.FAILED
        run.completed_at = _now()
        logger.warning("workflow run %s could not resume: %s", run.id, exc)


async def _start_run_for_trigger(
    session: AsyncSession, trigger: WorkflowTrigger, inbox_row: WorkflowTriggerInbox
) -> WorkflowRun | None:
    workflow = await session.get(Workflow, trigger.workflow_id)
    if workflow is None or workflow.current_published_version_id is None:
        logger.warning(
            "workflow_trigger %s references workflow %s with no published version",
            trigger.id,
            trigger.workflow_id,
        )
        return

    version = await session.get(WorkflowVersion, workflow.current_published_version_id)
    if version is None:
        return

    # `compiled_graph` (every WorkflowNodeTemplate-backed node already
    # resolved to a real registered node type - see engine.
    # template_resolution) is what a published version always has set;
    # `.graph` is the fallback only for defensive robustness against a
    # version published before this column existed.
    graph = WorkflowGraph.from_json(version.compiled_graph or version.graph)
    run = WorkflowRun(
        id=uuid.uuid4(),
        tenant_id=trigger.tenant_id,
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        trigger_event_ref=str(inbox_row.id),
        status=RunStatus.RUNNING,
        started_at=_now(),
    )
    session.add(run)
    await session.flush()

    try:
        await execute_run(session, run, graph, trigger_payload=inbox_row.payload)
    except RunLoopError as exc:
        run.status = RunStatus.FAILED
        run.completed_at = _now()
        logger.warning("workflow run %s could not start: %s", run.id, exc)
    return run


async def process_pending_now(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    """Dispatch `tenant_id`'s pending inbox rows immediately, in the
    caller's session, committing one event at a time - the serverless (Vercel) substitute
    for waiting on `_poll_forever_job`'s next pass.

    A serverless deployment has no persistent process to run that loop in
    (see `Settings.is_serverless`'s docstring), so `webhooks.py::_dispatch`
    calls this synchronously, right after its own webhook write commits,
    instead of relying on a background poller that would never actually
    run. The caller is responsible for `app.current_tenant_id` already
    being set on `session` for `tenant_id` (RLS) - same precondition
    `_process_tenant_inbox` always had, just met inline here instead of by
    `poll_once`'s per-tenant loop.
    """
    return await _process_tenant_inbox(session, tenant_id)


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


def register_outbox_poller(jobs: "JobQueue") -> None:
    """Register the poller's job handler. Call exactly once per process
    (see module docstring for the `main.py` wiring this can't do itself)."""
    jobs.register_handler(JOB_NAME, _poll_forever_job)


async def start_outbox_poller(
    jobs: "JobQueue",
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Kick off the recurring poll loop. Call once at startup, after
    `register_outbox_poller`."""
    await jobs.enqueue(
        JOB_NAME, jobs=jobs, session_factory=session_factory, interval_seconds=interval_seconds
    )
