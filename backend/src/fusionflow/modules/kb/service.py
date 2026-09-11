"""KB article domain logic.

None of these functions commit — routers own the transaction boundary.
Queries filter explicitly on `tenant_id` as defense-in-depth on top of RLS
(see `modules/customers/service.py` for the same convention).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.kb.models import KbArticle, KbArticleStatus
from fusionflow.modules.kb.schemas import KbArticleCreate, KbArticleUpdate


async def list_articles(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: KbArticleStatus | None = None,
    tag: str | None = None,
    limit: int | None = None,
) -> list[KbArticle]:
    stmt = select(KbArticle).where(KbArticle.tenant_id == tenant_id)
    if status is not None:
        stmt = stmt.where(KbArticle.status == status)
    if tag is not None:
        stmt = stmt.where(KbArticle.tags.any(tag))
    stmt = stmt.order_by(KbArticle.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def search_articles(
    session: AsyncSession, tenant_id: uuid.UUID, query: str, *, limit: int = 20
) -> list[KbArticle]:
    """Simple `ILIKE` keyword search over title/body - sufficient for "does
    this workflow's question match a KB article" without adding a
    full-text-search dependency (see this phase's plan)."""
    pattern = f"%{query}%"
    stmt = (
        select(KbArticle)
        .where(
            KbArticle.tenant_id == tenant_id,
            or_(KbArticle.title.ilike(pattern), KbArticle.body.ilike(pattern)),
        )
        .order_by(KbArticle.created_at.desc())
        .limit(limit)
    )
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def count_articles(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(KbArticle).where(KbArticle.tenant_id == tenant_id)
    return (await session.execute(stmt)).scalar_one()


async def get_article(session: AsyncSession, tenant_id: uuid.UUID, article_id: uuid.UUID) -> KbArticle | None:
    return (
        await session.execute(
            select(KbArticle).where(KbArticle.id == article_id, KbArticle.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def create_article(
    session: AsyncSession, tenant_id: uuid.UUID, payload: KbArticleCreate
) -> KbArticle:
    article = KbArticle(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        title=payload.title,
        body=payload.body,
        tags=payload.tags,
        status=payload.status,
    )
    session.add(article)
    await session.flush()
    return article


async def update_article(
    session: AsyncSession, article: KbArticle, payload: KbArticleUpdate
) -> KbArticle:
    if payload.title is not None:
        article.title = payload.title
    if payload.body is not None:
        article.body = payload.body
    if payload.tags is not None:
        article.tags = payload.tags
    if payload.status is not None:
        article.status = payload.status
    await session.flush()
    return article


async def delete_article(session: AsyncSession, article: KbArticle) -> None:
    await session.delete(article)
    await session.flush()
