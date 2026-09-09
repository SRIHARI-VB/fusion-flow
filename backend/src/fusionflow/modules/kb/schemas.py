from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.kb.models import KbArticleStatus


class KbArticleCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    status: KbArticleStatus = KbArticleStatus.DRAFT


class KbArticleUpdate(BaseModel):
    """Partial update — every field optional, unset fields are left alone."""

    title: str | None = Field(default=None, min_length=1, max_length=300)
    body: str | None = Field(default=None, min_length=1)
    tags: list[str] | None = None
    status: KbArticleStatus | None = None


class KbArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    tags: list[str]
    status: KbArticleStatus
    created_at: datetime
    updated_at: datetime
