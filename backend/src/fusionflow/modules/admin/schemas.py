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
    denial_reason: str | None = None


class DenyTenantRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


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
    denial_reason: str | None = None


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


class PlanResourceLimitOut(BaseModel):
    """One catalog resource key + this plan's configured limit - built by
    hand in `service.list_plan_resource_limits`, enriched with the full
    catalog so the editor can show an input for every resource, not just
    already-configured ones."""

    connector_type_id: uuid.UUID
    resource_key: str
    display_name: str
    max_count: int | None = None


class PlanResourceLimitIn(BaseModel):
    resource_key: str
    max_count: int | None = Field(default=None, ge=0)


class PlanResourceLimitsSetRequest(BaseModel):
    limits: list[PlanResourceLimitIn] = Field(default_factory=list)


class TenantResourceLimitOut(BaseModel):
    connector_type_id: uuid.UUID
    resource_key: str
    display_name: str
    limit: int | None = None
    source: str


class ResourceLimitOverrideRequest(BaseModel):
    max_count: int = Field(ge=0)


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
    # Lets the admin UI distinguish a request created as part of a brand-new
    # signup application (business still PENDING_APPROVAL) from one an
    # already-active tenant filed later for an additional module/connector.
    business_status: BusinessStatus
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


class TenantModuleAccessOut(BaseModel):
    """One catalog row's resolved access for one tenant - built by hand in
    `service.get_tenant_module_access`, not `from_attributes`'d."""

    connector_type_id: uuid.UUID
    connector_type_key: str
    display_name: str
    category: str
    access_status: str
    has_override: bool
    override_granted: bool | None = None
    role_restrictions: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    dependents: list[str] = Field(default_factory=list)


class RevokeImpactDependentOut(BaseModel):
    key: str
    display_name: str
    access_status: str


class RevokeImpactWorkflowOut(BaseModel):
    id: uuid.UUID
    name: str


class RevokeImpactRoleOut(BaseModel):
    role: str


class ConnectorRevokeImpactOut(BaseModel):
    type_key: str
    display_name: str
    dependents: list[RevokeImpactDependentOut]
    published_workflows: list[RevokeImpactWorkflowOut]
    connected_instances: int
    role_restrictions: list[RevokeImpactRoleOut]
    active_users_count: int


class ConnectorAccessOverrideRequest(BaseModel):
    granted: bool
    reason: str | None = Field(default=None, max_length=1000)


class ConnectorAccessOverrideOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    connector_type_id: uuid.UUID
    granted: bool
    set_by: uuid.UUID | None = None
    reason: str | None = None
    created_at: datetime
    updated_at: datetime


class BillingUsageOut(BaseModel):
    """Placeholder payload - phase 1 has no metering/billing model yet.

    Shape is deliberately provisional; real usage metering is Phase 2+ per
    the plan's roadmap ("...deeper workflow node/condition library ->
    billing/usage metering").
    """

    available: bool = False
    reason: str = "Billing/usage metering is not implemented yet (Phase 2+ per the plan)"
    tenants_count: int = 0


class WorkflowNodeTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    label: str
    description: str | None = None
    category: str
    base_node_type: str
    icon: str | None = None
    default_config: dict[str, Any] = Field(default_factory=dict)
    config_schema_overrides: dict[str, Any] | None = None
    is_active: bool
    required_connector_type_key: str | None = None
    created_at: datetime


class AdminNodeTypeSummaryOut(BaseModel):
    """One registered workflow node/trigger type, for the admin panel's
    `base_node_type` picker when authoring a `WorkflowNodeTemplate` -
    deliberately minimal (no `config_schema`/`output_schema`/etc.) since
    this is only ever used to populate a dropdown, not to render a config
    form. Sourced live from `workflows.service.list_node_types()` (the raw
    engine registry, not tenant-filtered) so it can never go stale the way
    a hand-maintained list on the frontend would."""

    node_type: str
    kind: str
    label: str
    category: str


class WorkflowNodeTemplateCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str = Field(default="Integrations", max_length=80)
    base_node_type: str = Field(min_length=1, max_length=150)
    icon: str | None = Field(default=None, max_length=80)
    default_config: dict[str, Any] = Field(default_factory=dict)
    config_schema_overrides: dict[str, Any] | None = None
    is_active: bool = True
    required_connector_type_key: str | None = Field(default=None, max_length=80)


class WorkflowNodeTemplateUpdateRequest(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    icon: str | None = Field(default=None, max_length=80)
    default_config: dict[str, Any] | None = None
    config_schema_overrides: dict[str, Any] | None = None
    is_active: bool | None = None
    required_connector_type_key: str | None = Field(default=None, max_length=80)


class WorkflowStarterTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: str | None = None
    category: str
    icon: str | None = None
    graph_json: dict[str, Any]
    required_object_types: list[dict[str, Any]] | None = None
    setup_notes: str | None = None
    is_active: bool
    created_at: datetime


class WorkflowStarterTemplateSummaryOut(BaseModel):
    """The tenant-facing subset (`GET /workflows/starter-templates`) - just
    enough for a "start from a template" picker card. `graph_json`/
    `required_object_types` are instantiation details a tenant never needs
    to see directly (see `workflows.service.create_workflow_from_starter_template`,
    which reads the full row server-side)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: str | None = None
    category: str
    icon: str | None = None


class WorkflowStarterTemplateCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str = Field(default="General", max_length=80)
    icon: str | None = Field(default=None, max_length=80)
    graph_json: dict[str, Any]
    required_object_types: list[dict[str, Any]] | None = None
    setup_notes: str | None = Field(default=None, max_length=4000)
    is_active: bool = True


class WorkflowStarterTemplateUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    icon: str | None = Field(default=None, max_length=80)
    graph_json: dict[str, Any] | None = None
    required_object_types: list[dict[str, Any]] | None = None
    setup_notes: str | None = Field(default=None, max_length=4000)
    is_active: bool | None = None


class WorkflowComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: str | None = None
    category: str
    icon: str | None = None
    graph_fragment: dict[str, Any]
    required_object_types: list[dict[str, Any]] | None = None
    setup_notes: str | None = None
    is_active: bool
    created_at: datetime


class WorkflowComponentCreateRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str = Field(default="General", max_length=80)
    icon: str | None = Field(default=None, max_length=80)
    graph_fragment: dict[str, Any]
    required_object_types: list[dict[str, Any]] | None = None
    setup_notes: str | None = Field(default=None, max_length=4000)
    is_active: bool = True


class WorkflowComponentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    icon: str | None = Field(default=None, max_length=80)
    graph_fragment: dict[str, Any] | None = None
    required_object_types: list[dict[str, Any]] | None = None
    setup_notes: str | None = Field(default=None, max_length=4000)
    is_active: bool | None = None


# --- Validate (Part C: reuse existing validation logic, admin-side) ---------


class GraphValidationIssueOut(BaseModel):
    rule: str
    severity: str
    message: str
    node_id: str | None = None


class GraphValidationResultOut(BaseModel):
    issues: list[GraphValidationIssueOut] = Field(default_factory=list)
    required_connector_type_keys: list[str] = Field(default_factory=list)


class ValidateStarterTemplateRequest(BaseModel):
    graph_json: dict[str, Any]


class ValidateComponentRequest(BaseModel):
    graph_fragment: dict[str, Any]
