"""Tenant-facing DTOs for `BusinessTemplate` ("starter kit").

Deliberately thinner than `modules.admin.schemas.BusinessTemplateOut`: no
`created_at`, and connector types are exposed by `key` (what the onboarding
picker and `connectors` UI actually key off of) rather than by internal id.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.connectors.schemas import ConnectorTypeOut


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


class SignupCatalogOut(BaseModel):
    """`GET /business-templates/catalog` - the one genuinely unauthenticated
    endpoint in this feature: the signup form needs to show templates and
    the connector/module catalog before any session exists. `connector_types`
    entries always carry `access_status="not_requested"` - that field has no
    meaning pre-signup."""

    templates: list[BusinessTemplateOut] = Field(default_factory=list)
    connector_types: list[ConnectorTypeOut] = Field(default_factory=list)
