"""Transactional outbox writer.

`publish_trigger_event` only INSERTs a `workflow_trigger_inbox` row and
flushes — it never commits. Callers (webhook receivers, fixed-connector
domain services such as `order.created`) call this inside the *same*
session/transaction as their own domain write, then commit once, so a
crash before commit loses both writes together and a crash after commit
has durably recorded both. No lost trigger events (the transactional
outbox pattern named in the plan's "Workflow Engine" section).

The outbox poller (`outbox_poller.py`) is the other half: it reads
unprocessed rows this function wrote and turns them into `workflow_runs`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.workflows.models import RunStatus, WorkflowRun, WorkflowTriggerInbox


async def _find_existing_by_dedupe_key(
    session: AsyncSession, *, tenant_id: uuid.UUID, dedupe_key: str
) -> WorkflowTriggerInbox | None:
    return (
        await session.execute(
            select(WorkflowTriggerInbox).where(
                WorkflowTriggerInbox.tenant_id == tenant_id,
                WorkflowTriggerInbox.dedupe_key == dedupe_key,
            )
        )
    ).scalar_one_or_none()


async def _insert_or_get(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    connector_instance_id: uuid.UUID | None,
    dedupe_key: str | None,
) -> WorkflowTriggerInbox:
    """Shared by `publish_trigger_event` and `publish_resume_event`: the
    dedupe-by-existing-row check plus the actual insert, so neither
    function repeats the lookup logic.

    The SELECT-then-INSERT below is not itself race-free: two requests
    (concurrent workers, or Meta's ~20s webhook redelivery landing on two
    workers at once) can both see `existing is None` and both attempt the
    INSERT, and only one wins the unique `(tenant_id, dedupe_key)`
    constraint (see `models.py`'s `uq_workflow_trigger_inbox_tenant_dedupe_key`).
    The loser's INSERT is wrapped in its own SAVEPOINT
    (`session.begin_nested()`) so the resulting `IntegrityError` only
    rolls back that nested SAVEPOINT instead of poisoning the caller's
    still-open outer transaction - this function only ever `flush()`es,
    never commits (see module docstring), so the caller must still be able
    to use `session` afterwards. On that race, re-fetch and return the
    winner's row, same as the plain dedupe-hit path above.
    """
    if dedupe_key is not None:
        existing = await _find_existing_by_dedupe_key(session, tenant_id=tenant_id, dedupe_key=dedupe_key)
        if existing is not None:
            return existing

        row = WorkflowTriggerInbox(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            event_type=event_type,
            payload=payload,
            connector_instance_id=connector_instance_id,
            dedupe_key=dedupe_key,
        )
        try:
            async with session.begin_nested():
                session.add(row)
                await session.flush()
        except IntegrityError:
            existing = await _find_existing_by_dedupe_key(session, tenant_id=tenant_id, dedupe_key=dedupe_key)
            if existing is not None:
                return existing
            raise
        return row

    row = WorkflowTriggerInbox(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        event_type=event_type,
        payload=payload,
        connector_instance_id=connector_instance_id,
        dedupe_key=None,
    )
    session.add(row)
    await session.flush()
    return row


async def publish_trigger_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    connector_instance_id: uuid.UUID | None = None,
    dedupe_key: str | None = None,
) -> WorkflowTriggerInbox:
    """Write one outbox row. Does not commit — see module docstring.

    `dedupe_key`, when given, must be the provider's own delivery/event id
    (e.g. a webhook redelivery id) — the same idempotency-upsert precedent
    as `payments.upsert_payment_from_provider`'s `provider_ref` key,
    applied here to inbox rows instead of payment rows. If a row with the
    same `(tenant_id, dedupe_key)` already exists, that existing row is
    returned unchanged instead of inserting a duplicate, so a redelivered
    webhook can never double-fire a workflow run. Callers with no natural
    dedupe key (e.g. `order.created`) simply omit it.
    """
    return await _insert_or_get(
        session,
        tenant_id=tenant_id,
        event_type=event_type,
        payload=payload,
        connector_instance_id=connector_instance_id,
        dedupe_key=dedupe_key,
    )


async def find_pending_wait(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connector_instance_id: uuid.UUID,
    correlation_key: str,
) -> WorkflowRun | None:
    """Phase 8 Part A: does this customer (`correlation_key`, e.g. a phone
    number), on this connector instance, have a run currently paused
    waiting for exactly their next reply? Locks the row (`FOR UPDATE`) so
    a webhook handler can safely decide "resume" vs. "new trigger" without
    a race against a concurrent delivery for the same run.
    """
    return (
        await session.execute(
            select(WorkflowRun)
            .where(
                WorkflowRun.tenant_id == tenant_id,
                WorkflowRun.status == RunStatus.WAITING,
                WorkflowRun.waiting_connector_instance_id == connector_instance_id,
                WorkflowRun.waiting_correlation_key == correlation_key,
            )
            .with_for_update()
            .limit(1)
        )
    ).scalar_one_or_none()


async def publish_resume_event(
    session: AsyncSession,
    *,
    run: WorkflowRun,
    reply_payload: dict[str, Any],
    dedupe_key: str | None,
) -> WorkflowTriggerInbox:
    """Write a `workflow.resume`-typed outbox row for `run` instead of a
    normal trigger event — the outbox poller's `_process_tenant_inbox`
    routes this event type to `run_loop.resume_run` rather than starting a
    new run. Same redelivery-safety discipline as `publish_trigger_event`
    (`dedupe_key` is typically the inbound message's own delivery id)."""
    return await _insert_or_get(
        session,
        tenant_id=run.tenant_id,
        event_type="workflow.resume",
        payload={"run_id": str(run.id), "reply": reply_payload},
        connector_instance_id=run.waiting_connector_instance_id,
        dedupe_key=dedupe_key,
    )
