"""Schedule poller — recurring/scheduled bulk-messaging support's other
polling loop, sibling to `outbox_poller.py`. Reads due, active
`WorkflowSchedule` rows, resolves each one's `recipient_source` into a
concrete phone-number list, starts one `WorkflowRun` per due schedule
(trigger_payload={"recipients": [...]}), and either recomputes
`next_run_at` (daily/weekly/monthly) or deactivates the schedule
(frequency="once", which never fires twice). Written against the same
`JobQueue` protocol from `core/jobs.py` as `outbox_poller.py`, for the same
"provision but skip in dev" reason - see that file's module docstring.

Startup wiring lives in `main.py`'s `lifespan`, right after the existing
outbox-poller lines:

    register_schedule_poller(app.state.jobs)
    await start_schedule_poller(app.state.jobs)

Cross-tenant iteration: this poller, like `outbox_poller.py`, has to look
across every tenant on each pass (a schedule can be due for any tenant at
any moment) - it uses the exact same "read `businesses` for the candidate
tenant id list, then `set_tenant_context` + a per-tenant scoped query" shape
`outbox_poller.poll_once` already uses, rather than the unscoped/BYPASSRLS
engine (`db/session.py::unscoped_session_factory`) - that engine is
reserved for the narrow pre-tenant-context lookups `db/session.py`'s
docstring describes (OAuth/webhook tenant resolution), not general
business logic, and every `workflow_schedules` row is legitimately
tenant-scoped data this poller reads *after* establishing that tenant's
own RLS context, exactly like the outbox poller reads
`workflow_trigger_inbox` rows.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fusionflow.db.session import async_session_factory, set_tenant_context
from fusionflow.modules.tenancy.models import Business
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.module_registry import resolve_adapter
from fusionflow.modules.workflows.engine.run_loop import RunLoopError, execute_run
from fusionflow.modules.workflows.models import (
    RunStatus,
    Workflow,
    WorkflowRun,
    WorkflowSchedule,
    WorkflowVersion,
    compute_next_run_at,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fusionflow.core.jobs import JobQueue

logger = logging.getLogger(__name__)

JOB_NAME = "workflows.schedule_poll"
DEFAULT_INTERVAL_SECONDS = 30.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _get_field(row: dict[str, Any], path: str) -> Any:
    """Same dotted-path field lookup `nodes/whatsapp_ask_choice.py::_get_field`
    uses to resolve `label_field`/`value_field` against a module row -
    duplicated here (not imported) since it's a tiny private helper, not
    shared engine machinery."""
    current: Any = row
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


async def poll_once(
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
) -> int:
    """One pass over every tenant. Returns the number of schedules fired.

    Unlike `outbox_poller.poll_once`, this does not first check for a
    "has anything pending" cheap query per tenant before doing real work -
    `workflow_schedules` rows are expected to be far fewer per tenant than
    inbox rows, so the extra existence-check round trip isn't worth it;
    `_process_tenant_schedules`'s own indexed `next_run_at <=` filter is
    already the cheap check.
    """
    async with session_factory() as session:
        tenant_ids = (await session.execute(select(Business.id))).scalars().all()

    fired = 0
    for tenant_id in tenant_ids:
        async with session_factory() as session:
            await set_tenant_context(session, tenant_id)
            fired += await _process_tenant_schedules(session, tenant_id)
    return fired


async def _process_tenant_schedules(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    # `with_for_update(skip_locked=True)`: same multi-process safety
    # property as `outbox_poller._process_tenant_inbox` - two concurrent
    # pollers divide due schedules instead of double-firing one.
    rows = (
        await session.execute(
            select(WorkflowSchedule)
            .where(
                WorkflowSchedule.tenant_id == tenant_id,
                WorkflowSchedule.is_active.is_(True),
                WorkflowSchedule.next_run_at <= _now(),
            )
            .with_for_update(skip_locked=True)
        )
    ).scalars().all()

    for schedule in rows:
        await _fire_schedule(session, schedule)

    if rows:
        await session.commit()
    return len(rows)


async def _resolve_recipients(
    session: AsyncSession, tenant_id: uuid.UUID, recipient_source: dict[str, Any]
) -> list[str]:
    """`{"kind": "static", "phone_numbers": [...]}` is used as-is;
    `{"kind": "module", "module": ..., "filters": {...}, "phone_field": ...}`
    re-runs a live query through the same `resolve_adapter`/
    `ModuleQueryAdapter.list` lookup `nodes/whatsapp_ask_choice.py`'s
    `ModuleSource` branch uses at execute-time, so a schedule's recipient
    set always reflects the module's current rows, not a stale snapshot
    from when the schedule was created."""
    kind = recipient_source.get("kind")
    if kind == "static":
        return [str(n) for n in recipient_source.get("phone_numbers") or []]

    if kind == "module":
        module_key = recipient_source.get("module")
        adapter = await resolve_adapter(session, tenant_id=tenant_id, module_key=module_key)
        if adapter is None:
            logger.warning("workflow_schedule references unknown module %r", module_key)
            return []
        filters = recipient_source.get("filters") or {}
        rows = await adapter.list(session, tenant_id=tenant_id, filters=filters, limit=1000)
        phone_field = recipient_source.get("phone_field", "phone")
        recipients = []
        for row in rows:
            value = _get_field(row, phone_field)
            if value:
                recipients.append(str(value))
        return recipients

    logger.warning("workflow_schedule has unknown recipient_source kind %r", kind)
    return []


async def _fire_schedule(session: AsyncSession, schedule: WorkflowSchedule) -> None:
    recipients = await _resolve_recipients(session, schedule.tenant_id, schedule.recipient_source)

    run_status = "started"
    workflow = await session.get(Workflow, schedule.workflow_id)
    if workflow is None or workflow.current_published_version_id is None:
        logger.warning(
            "workflow_schedule %s references workflow %s with no published version",
            schedule.id,
            schedule.workflow_id,
        )
        run_status = "failed"
    else:
        version = await session.get(WorkflowVersion, workflow.current_published_version_id)
        if version is None:
            run_status = "failed"
        else:
            # Same `compiled_graph or graph` fallback as
            # `outbox_poller._start_run_for_trigger` - see that function's
            # comment for why.
            graph = WorkflowGraph.from_json(version.compiled_graph or version.graph)
            run = WorkflowRun(
                id=uuid.uuid4(),
                tenant_id=schedule.tenant_id,
                workflow_id=workflow.id,
                workflow_version_id=version.id,
                trigger_event_ref=f"schedule:{schedule.id}",
                status=RunStatus.RUNNING,
                started_at=_now(),
            )
            session.add(run)
            await session.flush()

            try:
                await execute_run(session, run, graph, trigger_payload={"recipients": recipients})
            except RunLoopError as exc:
                run.status = RunStatus.FAILED
                run.completed_at = _now()
                run_status = "failed"
                logger.warning("workflow_schedule %s run %s could not start: %s", schedule.id, run.id, exc)
            if run.status == RunStatus.FAILED:
                run_status = "failed"

    fired_at = _now()
    schedule.last_run_at = fired_at
    schedule.last_run_status = run_status

    if schedule.frequency == "once":
        # Never recomputed/re-fired - see `compute_next_run_at`'s docstring.
        schedule.is_active = False
    else:
        schedule.next_run_at = compute_next_run_at(
            schedule.frequency,
            schedule.time_of_day,
            schedule.weekdays,
            schedule.day_of_month,
            schedule.timezone,
            after=fired_at,
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


def register_schedule_poller(jobs: "JobQueue") -> None:
    """Register the poller's job handler. Call exactly once per process
    (see module docstring for the `main.py` wiring this can't do itself)."""
    jobs.register_handler(JOB_NAME, _poll_forever_job)


async def start_schedule_poller(
    jobs: "JobQueue",
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
    interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
) -> None:
    """Kick off the recurring poll loop. Call once at startup, after
    `register_schedule_poller`."""
    await jobs.enqueue(
        JOB_NAME, jobs=jobs, session_factory=session_factory, interval_seconds=interval_seconds
    )
