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

Two safety properties added for multi-process/production correctness:
`_process_tenant_inbox` locks its inbox rows with `FOR UPDATE SKIP LOCKED`
so two concurrent pollers (a horizontal scale-out scenario) divide the
work instead of double-processing the same row, and `poll_once` only
visits tenants that actually have unprocessed inbox rows (one indexed
query) instead of scanning every tenant in `businesses` every cycle.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fusionflow.db.session import async_session_factory, set_tenant_context
from fusionflow.modules.tenancy.models import Business
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.run_loop import RunLoopError, execute_run
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


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if has_pending is None:
                continue
            processed += await _process_tenant_inbox(session, tenant_id)
    return processed


async def _process_tenant_inbox(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    # `with_for_update(skip_locked=True)`: if this app ever runs more than
    # one backend process, two pollers racing on the same tenant divide the
    # work instead of double-processing the same row (each locks out the
    # rows the other has already claimed instead of blocking on them).
    rows = (
        await session.execute(
            select(WorkflowTriggerInbox)
            .where(
                WorkflowTriggerInbox.tenant_id == tenant_id,
                WorkflowTriggerInbox.processed_at.is_(None),
            )
            .order_by(WorkflowTriggerInbox.created_at)
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()

    for inbox_row in rows:
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

        for trigger in matching:
            await _start_run_for_trigger(session, trigger, inbox_row)

        inbox_row.processed_at = _now()

    if rows:
        await session.commit()
    return len(rows)


async def _start_run_for_trigger(
    session: AsyncSession, trigger: WorkflowTrigger, inbox_row: WorkflowTriggerInbox
) -> None:
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

    graph = WorkflowGraph.from_json(version.graph)
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
