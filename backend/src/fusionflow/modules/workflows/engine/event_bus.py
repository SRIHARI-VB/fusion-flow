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
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.workflows.models import WorkflowTriggerInbox


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
    if dedupe_key is not None:
        existing = (
            await session.execute(
                select(WorkflowTriggerInbox).where(
                    WorkflowTriggerInbox.tenant_id == tenant_id,
                    WorkflowTriggerInbox.dedupe_key == dedupe_key,
                )
            )
        ).scalar_one_or_none()
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
    session.add(row)
    await session.flush()
    return row
