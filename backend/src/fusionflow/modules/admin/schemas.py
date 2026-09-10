from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.tenancy.models import BusinessStatus, MembershipRole


class TenantListItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    vertical: str | None = None
    status: BusinessStatus
    member_count: int
    created_at: datetime


class TenantMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    email: str
    role: MembershipRole
    invited_at: datetime
    accepted_at: datetime | None = None


class TenantDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    vertical: str | None = None
    status: BusinessStatus
    onboarding_completed_at: datetime | None = None
    created_at: datetime
    memberships: list[TenantMembershipOut]


class ConnectorHealthItemOut(BaseModel):
    """One `connector_instances` row's health, as seen cross-tenant by an admin."""

    id: uuid.UUID
    connector_type_key: str
    state: str
    last_webhook_at: datetime | None = None
    last_sync_at: datetime | None = None


class ConnectorHealthOut(BaseModel):
    """Wrapper that degrades gracefully if `modules.connectors` isn't built yet.

    `available=False` means the `connectors` module (specifically
    `ConnectorInstance`) doesn't exist in this checkout yet - see
    `modules/admin/service.py::get_tenant_connector_health` - not that the
    tenant has zero connectors.
    """

    available: bool
    reason: str | None = None
    connectors: list[ConnectorHealthItemOut] = Field(default_factory=list)


class SuspendTenantRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ImpersonateRequest(BaseModel):
    target_user_id: uuid.UUID
    reason: str = Field(min_length=1, max_length=500)


class ImpersonateResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    impersonated: bool = True
    acting_admin_id: uuid.UUID
    target_user_id: uuid.UUID
    target_business_id: uuid.UUID
    impersonation_session_id: uuid.UUID


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_user_id: uuid.UUID | None = None
    actor_is_platform_admin: bool
    tenant_id: uuid.UUID | None = None
    action: str
    target_type: str | None = None
    target_id: str | None = None
    extra_metadata: dict[str, Any] | None = None
    ip_address: str | None = None
    created_at: datetime


class AuditLogPage(BaseModel):
    items: list[AuditLogOut]
    total: int


class FeatureFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    description: str | None = None
    is_global_default: bool
    created_at: datetime


class FeatureFlagCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_global_default: bool = False


class FeatureFlagUpdateRequest(BaseModel):
    description: str | None = Field(default=None, max_length=2000)
    is_global_default: bool | None = None


class FeatureFlagCatalogItemOut(BaseModel):
    """One entry of `service.KNOWN_FEATURE_FLAGS` - what the admin "New
    flag" dropdown offers instead of a free-text key field."""

    key: str
    label: str
    description: str
    gates_real_behavior: bool


class FeatureFlagOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    feature_flag_id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    enabled: bool


class FeatureFlagOverrideUpsertRequest(BaseModel):
    """`tenant_id=None` sets/replaces the flag's global override."""

    tenant_id: uuid.UUID | None = None
    enabled: bool


class FieldTemplateOut(BaseModel):
    """Read-only projection of `custom_fields.models.FieldTemplate`.

    Deliberately summarizes `fields` down to a count rather than echoing the
    full JSONB spec list - this admin module treats template *content*
    editing as out of scope for now (see service.py's docstring); the
    per-tenant `apply_template` flow that consumes the full field list lives
    in `modules.custom_fields`, not here.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vertical: str
    entity_type: str
    name: str
    version: int
    is_global: bool
    field_count: int


class FieldTemplatesUnavailableOut(BaseModel):
    available: bool = False
    reason: str = "modules.custom_fields.FieldTemplate does not exist in this checkout yet"


class PlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    is_default: bool
    created_at: datetime


class PlanCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    is_default: bool = False


class PlanUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    is_default: bool | None = None


class PlanFeatureFlagIn(BaseModel):
    feature_flag_id: uuid.UUID
    enabled: bool


class PlanFeatureFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_id: uuid.UUID
    feature_flag_id: uuid.UUID
    enabled: bool


class PlanFeatureFlagsSetRequest(BaseModel):
    flags: list[PlanFeatureFlagIn] = Field(default_factory=list)


class BusinessTemplateOut(BaseModel):
    """Admin-facing projection - richer than the tenant-facing
    `modules.business_templates.schemas.BusinessTemplateOut` (which omits
    `created_at` and exposes connector types by `key`, not `id`)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: str | None = None
    vertical: str | None = None
    plan_id: uuid.UUID | None = None
    is_active: bool
    created_at: datetime
    connector_type_ids: list[uuid.UUID] = Field(default_factory=list)


class BusinessTemplateCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    vertical: str | None = Field(default=None, max_length=80)
    plan_id: uuid.UUID | None = None
    is_active: bool = True
    connector_type_ids: list[uuid.UUID] = Field(default_factory=list)


class BusinessTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    vertical: str | None = Field(default=None, max_length=80)
    plan_id: uuid.UUID | None = None
    is_active: bool | None = None
    connector_type_ids: list[uuid.UUID] | None = None


class AssignTenantPlanRequest(BaseModel):
    """`plan_id=None` unassigns the tenant's plan."""

    plan_id: uuid.UUID | None = None


class ConnectorAccessRequestAdminOut(BaseModel):
    """Cross-tenant projection - built by hand in `service.list_connector_access_requests`
    from a joined `(ConnectorAccessRequest, Business, ConnectorType, User)` row tuple read
    over `unscoped_session_factory`, so this is never `from_attributes`'d off a single ORM
    instance the way most `*Out` schemas here are."""

    id: uuid.UUID
    tenant_id: uuid.UUID
    business_name: str
    connector_type_id: uuid.UUID
    connector_type_key: str
    status: str
    reason: str | None = None
    requested_by: uuid.UUID
    requested_by_email: str | None = None
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class ConnectorTypeCatalogOut(BaseModel):
    """Minimal projection of the global `connector_types` catalog - just
    enough for the admin "pick connectors for this bundle" UI. The full
    `ConnectorTypeOut` (with `config_schema` etc.) lives in
    `modules.connectors.schemas` and isn't reachable from `/api/admin/*`
    (that surface has no tenant context - see this task's report)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    display_name: str
    category: str


class ConnectorAccessRequestReviewOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    status: str
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None


class BillingUsageOut(BaseModel):
    """Placeholder payload - phase 1 has no metering/billing model yet.

    Shape is deliberately provisional; real usage metering is Phase 2+ per
    the plan's roadmap ("...deeper workflow node/condition library ->
    billing/usage metering").
    """

    available: bool = False
    reason: str = "Billing/usage metering is not implemented yet (Phase 2+ per the plan)"
    tenants_count: int = 0
