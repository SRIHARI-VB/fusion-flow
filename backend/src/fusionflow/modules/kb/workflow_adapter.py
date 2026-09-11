"""`ModuleQueryAdapter` registration for `kb` (knowledge base articles) -
full CRUD. `filters.query` routes `list` through `search_articles`'s
title/body `ILIKE` search instead of the plain listing - the one module
whose generic `list` filter set includes a free-text search, per the
Phase 6 plan's KB scope.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.kb import service as kb_service
from fusionflow.modules.kb.models import KbArticleStatus
from fusionflow.modules.kb.schemas import KbArticleCreate, KbArticleOut, KbArticleUpdate
from fusionflow.modules.workflows.engine.module_registry import ModuleQueryAdapter, registry


class KbQueryAdapter(ModuleQueryAdapter):
    module_key = "kb"

    async def list(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        query = filters.get("query")
        if query:
            items = await kb_service.search_articles(session, tenant_id, query, limit=limit)
            return [KbArticleOut.model_validate(item).model_dump(mode="json") for item in items]

        status_value = filters.get("status")
        items = await kb_service.list_articles(
            session,
            tenant_id,
            status=KbArticleStatus(status_value) if status_value else None,
            tag=filters.get("tag"),
            limit=limit,
        )
        return [KbArticleOut.model_validate(item).model_dump(mode="json") for item in items]

    async def get(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> dict[str, Any] | None:
        item = await kb_service.get_article(session, tenant_id, item_id)
        return KbArticleOut.model_validate(item).model_dump(mode="json") if item else None

    async def create(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any]:
        payload = KbArticleCreate.model_validate(fields)
        item = await kb_service.create_article(session, tenant_id, payload)
        return KbArticleOut.model_validate(item).model_dump(mode="json")

    async def update(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        item = await kb_service.get_article(session, tenant_id, item_id)
        if item is None:
            return None
        payload = KbArticleUpdate.model_validate(fields)
        updated = await kb_service.update_article(session, item, payload)
        return KbArticleOut.model_validate(updated).model_dump(mode="json")


registry.register(KbQueryAdapter())
