"""Media Library domain logic.

None of these functions commit - routers own the transaction boundary
(see `modules/customers/service.py` for the same convention).
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.media_library.models import MediaAsset


async def list_media_assets(session: AsyncSession, *, tenant_id: uuid.UUID) -> Sequence[MediaAsset]:
    stmt = (
        select(MediaAsset)
        .where(MediaAsset.tenant_id == tenant_id)
        .order_by(MediaAsset.created_at.desc())
    )
    return (await session.execute(stmt)).scalars().all()


async def get_media_asset(
    session: AsyncSession, *, tenant_id: uuid.UUID, media_asset_id: uuid.UUID
) -> MediaAsset | None:
    return (
        await session.execute(
            select(MediaAsset).where(
                MediaAsset.id == media_asset_id, MediaAsset.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()


async def create_media_asset(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    url: str,
    filename: str,
    content_type: str,
    size_bytes: int,
    source: str,
) -> MediaAsset:
    media_asset = MediaAsset(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        url=url,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        source=source,
    )
    session.add(media_asset)
    await session.flush()
    return media_asset


async def delete_media_asset(session: AsyncSession, media_asset: MediaAsset) -> None:
    """Deletes only this catalog row - never touches the underlying R2
    object, which is out of scope for this module (a catalog, not the
    storage layer)."""
    await session.delete(media_asset)
    await session.flush()
