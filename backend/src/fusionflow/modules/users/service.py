"""Per-user sidebar layout persistence.

Pure UI personalization, scoped to `user_id` - not a tenant entitlement
(those live in `modules/connectors/`). None of these functions commit -
routers own the transaction boundary (see `modules/quick_replies/service.py`
for the same convention).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.users.models import UserSidebarLayout
from fusionflow.modules.users.schemas import SidebarLayout


async def _get_row(session: AsyncSession, *, user_id: uuid.UUID) -> UserSidebarLayout | None:
    return (
        await session.execute(
            select(UserSidebarLayout).where(UserSidebarLayout.user_id == user_id)
        )
    ).scalar_one_or_none()


async def get_sidebar_layout(session: AsyncSession, *, user_id: uuid.UUID) -> SidebarLayout | None:
    """The user's saved layout, or `None` if they have never saved one.

    `None` is returned cleanly (no exception) both when no row exists yet
    and when a row exists with `layout IS NULL` - both mean "use defaults".
    """
    row = await _get_row(session, user_id=user_id)
    if row is None or row.layout is None:
        return None
    return SidebarLayout.model_validate(row.layout)


async def save_sidebar_layout(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    layout: SidebarLayout | None,
) -> SidebarLayout | None:
    """Upsert the user's layout row. `layout=None` resets to defaults."""
    raw = layout.model_dump(mode="json") if layout is not None else None
    row = await _get_row(session, user_id=user_id)
    if row is None:
        row = UserSidebarLayout(id=uuid.uuid4(), tenant_id=tenant_id, user_id=user_id, layout=raw)
        session.add(row)
    else:
        row.tenant_id = tenant_id
        row.layout = raw
    await session.flush()
    return layout
