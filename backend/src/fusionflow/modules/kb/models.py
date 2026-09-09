"""KbArticle model — the fifth fixed connector (M2)."""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import ARRAY, Enum, String, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class KbArticleStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class KbArticle(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "kb_articles"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False, default=list, server_default="{}")
    status: Mapped[KbArticleStatus] = mapped_column(
        Enum(KbArticleStatus, name="kb_article_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=KbArticleStatus.DRAFT,
        server_default=KbArticleStatus.DRAFT.value,
    )
