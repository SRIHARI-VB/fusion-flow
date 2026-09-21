"""Quick Reply domain logic.

None of these functions commit — routers own the transaction boundary (see
`modules/customers/service.py` for the same convention).

Every query filters explicitly on `tenant_id` in addition to relying on
Postgres RLS (`SET LOCAL app.current_tenant_id`, applied by
`get_tenant_context`). The explicit filter is defense-in-depth, not the
primary isolation mechanism — see the plan's Risk #2 on `SET LOCAL`.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.quick_replies.models import QuickReply
from fusionflow.modules.quick_replies.schemas import QuickReplyCreate, QuickReplyUpdate


async def list_quick_replies(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> Sequence[QuickReply]:
    stmt = (
        select(QuickReply)
        .where(QuickReply.tenant_id == tenant_id)
        .order_by(QuickReply.title)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_quick_reply(
    session: AsyncSession, *, tenant_id: uuid.UUID, quick_reply_id: uuid.UUID
) -> QuickReply | None:
    return (
        await session.execute(
            select(QuickReply).where(
                QuickReply.id == quick_reply_id, QuickReply.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()


async def create_quick_reply(
    session: AsyncSession, *, tenant_id: uuid.UUID, payload: QuickReplyCreate
) -> QuickReply:
    quick_reply = QuickReply(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        title=payload.title,
        body=payload.body,
    )
    session.add(quick_reply)
    await session.flush()
    return quick_reply


async def update_quick_reply(
    session: AsyncSession, quick_reply: QuickReply, *, payload: QuickReplyUpdate
) -> QuickReply:
    """Apply a partial update in place. Does not commit."""
    if payload.title is not None:
        quick_reply.title = payload.title
    if payload.body is not None:
        quick_reply.body = payload.body
    await session.flush()
    return quick_reply


async def delete_quick_reply(session: AsyncSession, quick_reply: QuickReply) -> None:
    await session.delete(quick_reply)
    await session.flush()
