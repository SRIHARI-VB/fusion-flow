"""KB article domain logic.

None of these functions commit — routers own the transaction boundary.
Queries filter explicitly on `tenant_id` as defense-in-depth on top of RLS
(see `modules/customers/service.py` for the same convention).
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.kb.models import KbArticle
from fusionflow.modules.kb.schemas import KbArticleCreate, KbArticleUpdate


async def list_articles(session: AsyncSession, tenant_id: uuid.UUID) -> list[KbArticle]:
    rows = await session.execute(
        select(KbArticle).where(KbArticle.tenant_id == tenant_id).order_by(KbArticle.created_at.desc())
    )
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
