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

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.workflows.models import WorkflowTriggerInbox


async def publish_trigger_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    event_type: str,
    payload: dict[str, Any],
    connector_instance_id: uuid.UUID | None = None,
) -> WorkflowTriggerInbox:
    """Write one outbox row. Does not commit — see module docstring."""
    row = WorkflowTriggerInbox(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        event_type=event_type,
        payload=payload,
        connector_instance_id=connector_instance_id,
    )
    session.add(row)
    await session.flush()
    return row
