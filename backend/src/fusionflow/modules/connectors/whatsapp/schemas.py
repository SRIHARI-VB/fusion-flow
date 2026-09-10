from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.connectors.whatsapp.models import WhatsAppTemplateCategory, WhatsAppTemplateStatus


class WhatsAppTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_instance_id: uuid.UUID
    name: str
    language: str
    category: WhatsAppTemplateCategory
    status: WhatsAppTemplateStatus
    components: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class WhatsAppTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    language: str = Field(min_length=1, max_length=20, description="e.g. 'en_US'")
    category: WhatsAppTemplateCategory
    status: WhatsAppTemplateStatus = WhatsAppTemplateStatus.APPROVED
    components: dict[str, Any] = Field(default_factory=dict)


class WhatsAppTemplateUpdateRequest(BaseModel):
    category: WhatsAppTemplateCategory | None = None
    status: WhatsAppTemplateStatus | None = None
    components: dict[str, Any] | None = None
