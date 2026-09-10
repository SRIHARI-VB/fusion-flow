"""`/api/v1/kb-articles` — the `kb_articles` fixed connector (M2).

Not mounted here — see `api.py`'s docstring; the integration wave mounts
`router` from this module under the `/api/v1` group.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.kb import service as kb_service
from fusionflow.modules.kb.schemas import KbArticleCreate, KbArticleOut, KbArticleUpdate

router = APIRouter(prefix="/kb-articles", tags=["kb"])


@router.get("", response_model=list[KbArticleOut])
async def list_kb_articles(session: SessionDep, context: TenantContextDep) -> list[KbArticleOut]:
    articles = await kb_service.list_articles(session, context.tenant_id)
    return [KbArticleOut.model_validate(article) for article in articles]


@router.post("", response_model=KbArticleOut, status_code=status.HTTP_201_CREATED)
async def create_kb_article(
    payload: KbArticleCreate, session: SessionDep, context: TenantContextDep
) -> KbArticleOut:
    article = await kb_service.create_article(session, context.tenant_id, payload)
    await commit_and_keep_tenant_context(session)
    await session.refresh(article)
    return KbArticleOut.model_validate(article)


@router.get("/{article_id}", response_model=KbArticleOut)
async def get_kb_article(
    article_id: uuid.UUID, session: SessionDep, context: TenantContextDep
) -> KbArticleOut:
    article = await kb_service.get_article(session, context.tenant_id, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    return KbArticleOut.model_validate(article)


@router.patch("/{article_id}", response_model=KbArticleOut)
async def update_kb_article(
    article_id: uuid.UUID,
    payload: KbArticleUpdate,
    session: SessionDep,
    context: TenantContextDep,
) -> KbArticleOut:
    article = await kb_service.get_article(session, context.tenant_id, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    article = await kb_service.update_article(session, article, payload)
    await commit_and_keep_tenant_context(session)
    await session.refresh(article)
    return KbArticleOut.model_validate(article)


@router.delete("/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_kb_article(
    article_id: uuid.UUID, session: SessionDep, context: TenantContextDep
) -> None:
    article = await kb_service.get_article(session, context.tenant_id, article_id)
    if article is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Article not found")
    await kb_service.delete_article(session, article)
    await commit_and_keep_tenant_context(session)
