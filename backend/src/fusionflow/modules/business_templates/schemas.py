"""Tenant-facing DTOs for `BusinessTemplate` ("starter kit").

Deliberately thinner than `modules.admin.schemas.BusinessTemplateOut`: no
`created_at`, and connector types are exposed by `key` (what the onboarding
picker and `connectors` UI actually key off of) rather than by internal id.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field


class BusinessTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: str | None = None
    vertical: str | None = None
    plan_id: uuid.UUID | None = None
    is_active: bool
    connector_type_keys: list[str] = Field(default_factory=list)


class ApplyBusinessTemplateResponse(BaseModel):
    business_template_id: uuid.UUID
    vertical: str | None = None
