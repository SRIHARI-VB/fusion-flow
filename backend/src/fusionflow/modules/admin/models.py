"""Super-admin platform models: audit log, feature flags, impersonation.

All four tables here are *platform-level* and deliberately NOT
tenant-RLS-scoped (see the plan's Core Data Model: "platform tables such as
users, businesses, audit_log and feature_flags sit outside RLS") - an admin
auditing a tenant's action, or a global feature-flag default, has no single
`tenant_id` to filter itself on, and `GET /api/admin/audit-log` is a
cross-tenant view by definition. None of these get a `TenantScopedMixin`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class AuditLog(Base):
    """One row per completed `/api/admin/*` request.

    Written generically by `modules/admin/audit.py::AuditLoggingRoute`, not
    by individual endpoint handlers - see that module for how `action`/
    `target_type`/`target_id` are derived from the request itself.

    Append-only by convention: nothing in this module updates or deletes a
    row once written - that is what makes it usable as an audit trail.
    `actor_user_id`/`tenant_id` use `ondelete="SET NULL"` rather than
    CASCADE so a later user/business deletion can never silently erase
    audit history.
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    target_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    # Named `extra_metadata` in Python - `metadata` is reserved on every
    # SQLAlchemy Declarative class (it's `Base.metadata`). The `mapped_column`
    # first positional arg pins the actual DB column name back to `metadata`.
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class FeatureFlag(Base, TimestampMixin):
    """Catalog of platform feature flags - fine-grained behavior toggles
    *inside* an already-accessible module (e.g. `advanced_workflows`
    gating one experimental node type in the workflow palette), distinct
    from whole-module access which lives in `modules.connectors.models.ConnectorType`
    instead - see `modules.admin.service.KNOWN_FEATURE_FLAGS`'s docstring
    for where the line is drawn."""

    __tablename__ = "feature_flags"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_global_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class FeatureFlagOverride(Base, TimestampMixin):
    """One override of a flag, either global (`tenant_id IS NULL`) or per-tenant.

    Resolution order (see `service.is_feature_enabled`): per-tenant override
    > global override (`tenant_id IS NULL`) > `FeatureFlag.is_global_default`.
    """

    __tablename__ = "feature_flag_overrides"
    __table_args__ = (
        UniqueConstraint(
            "feature_flag_id", "tenant_id", name="uq_feature_flag_override_flag_tenant"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_flag_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # NULL = a global override (beats FeatureFlag.is_global_default for every
    # tenant); set = scoped to that one tenant only.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class ImpersonationSession(Base):
    """Record of one platform-admin impersonation grant.

    `jwt_jti` ties the minted access token back to this row so that any
    action taken while impersonating still attributes to the real admin in
    the audit log (see the plan's Auth Flow / Super admin auth paragraph).
    """

    __tablename__ = "impersonation_sessions"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    platform_admin_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_business_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    jwt_jti: Mapped[str] = mapped_column(String(64), nullable=False, index=True)


# --- Plans / business templates / connector entitlements --------------------
#
# Per the plan's "Business templates, connector access requests, and plan
# entitlements" item: all four tables below are *global catalog* tables,
# admin-managed, matching this module's own `FeatureFlag` and
# `modules.custom_fields.FieldTemplate` - none of them get a
# `TenantScopedMixin`. Only `connectors.models.ConnectorAccessRequest` (a
# genuinely per-tenant table) is tenant-scoped; it lives in
# `modules.connectors.models`, not here, since it's the thing
# `modules.connectors.service.connect()` gates on.


class Plan(Base, TimestampMixin):
    """A billing/entitlement tier (e.g. "starter", "pro"). Global catalog."""

    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")


class PlanFeatureFlag(Base, TimestampMixin):
    """One (plan, feature_flag) entitlement row - the plan tier inserted into
    `admin.service.is_feature_enabled`'s resolution order between a tenant
    override and the global override/default."""

    __tablename__ = "plan_feature_flags"
    __table_args__ = (
        UniqueConstraint("plan_id", "feature_flag_id", name="uq_plan_feature_flag"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_flag_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("feature_flags.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)


class PlanResourceLimit(Base, TimestampMixin):
    """One (plan, connector_type) resource-count ceiling - e.g. "the Starter
    plan allows at most 50 products". Keyed by `connector_types.id` (the
    same catalog `require_module_access` already gates modules by) rather
    than a new enum, so limits and module-gating share one vocabulary. No
    row for a given (plan, connector_type) pair means unlimited at the plan
    level - see `admin.service.get_resource_limit`'s resolution order."""

    __tablename__ = "plan_resource_limits"
    __table_args__ = (
        UniqueConstraint("plan_id", "connector_type_id", name="uq_plan_resource_limit"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("plans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_types.id", ondelete="CASCADE"), nullable=False, index=True
    )
    max_count: Mapped[int] = mapped_column(Integer, nullable=False)


class ResourceLimitOverride(Base, TenantScopedMixin, TimestampMixin):
    """One tenant's explicit resource-count ceiling, overriding whatever
    its plan (via `PlanResourceLimit`) would otherwise allow - the same
    "tenant override beats plan default" shape as `FeatureFlagOverride`/
    `PlanFeatureFlag`, applied to counts instead of booleans. No row means
    no tenant-specific override; resolution falls through to the plan.

    Genuinely per-tenant (like `modules.connectors.models.ConnectorAccessRequest`,
    not like the other global-catalog tables in this module) since
    `admin.service.get_resource_limit` is called from inside a tenant-scoped
    request (the enforcement dependency on a create route) and needs RLS to
    let that tenant see its own row - `TenantScopedMixin` + RLS, not a plain
    `tenant_id` FK column.
    """

    __tablename__ = "resource_limit_overrides"
    __table_args__ = (
        UniqueConstraint("tenant_id", "connector_type_id", name="uq_resource_limit_override_tenant_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_types.id", ondelete="CASCADE"), nullable=False, index=True
    )
    max_count: Mapped[int] = mapped_column(Integer, nullable=False)


class BusinessTemplate(Base, TimestampMixin):
    """A higher-level per-vertical "starter kit": a bundle of connector
    types (via `BusinessTemplateConnectorType`) plus an optional default
    plan, offered to a tenant during onboarding.

    Deliberately distinct from `modules.custom_fields.FieldTemplate` (an
    older, narrower per-entity-type custom-field bundle) - the onboarding
    "apply a template" step now applies both: this row's connector bundle
    is granted directly, and the matching `FieldTemplate`s for the same
    `vertical` are applied through the existing custom-fields flow.
    """

    __tablename__ = "business_templates"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    vertical: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class BusinessTemplateConnectorType(Base, TimestampMixin):
    """One (business_template, connector_type) bundle membership row.

    This is exactly the bundle `modules.connectors.service.connect()`
    checks a tenant's `Business.business_template_id` against before
    allowing a connect - being in this bundle is one of the two ways a
    tenant is entitled to a connector (the other being an `approved`
    `ConnectorAccessRequest`).
    """

    __tablename__ = "business_template_connector_types"
    __table_args__ = (
        UniqueConstraint(
            "business_template_id", "connector_type_id", name="uq_business_template_connector_type"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_template_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("business_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    connector_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_types.id", ondelete="CASCADE"), nullable=False, index=True
    )


class WorkflowNodeTemplate(Base, TimestampMixin):
    """Admin-managed palette entry over one of the workflow engine's
    generic executors (`connector.action`, `http.request`, ...) - the
    "new integration without a deploy" half of Part D's extensibility
    layer (see `modules.workflows.nodes.connector_action`'s module
    docstring for the other half, the adapter's own `perform_action`).

    Mirrors `BusinessTemplate`'s shape deliberately: this is the same
    admin-catalog-row-drives-behavior pattern already proven for
    `ConnectorType`/`BusinessTemplate`/`PlanFeatureFlag`/
    `PlanResourceLimit` in this codebase, applied to workflow node
    palette entries. Global, not tenant-scoped - like `BusinessTemplate`,
    every tenant sees the same active templates.
    """

    __tablename__ = "workflow_node_templates"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="Integrations")
    # The registered `NodeExecutor.node_type` this template wraps at
    # runtime (e.g. "connector.action", "http.request") - not validated
    # against the live registry at write time (an admin might add a
    # template before the corresponding executor ships in a deploy, or
    # the registry may differ between environments); `service.py`'s
    # palette-listing code is what actually resolves it, and simply skips
    # a template whose `base_node_type` isn't currently registered.
    base_node_type: Mapped[str] = mapped_column(String(150), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Phase 7 Part A: entitlement gate this template inherits/narrows - see
    # `engine.registry.NodeExecutor.required_connector_type_key`'s docstring.
    # Nullable: `None` means "inherit the base executor's own requirement"
    # (service.list_node_types_with_templates falls back to the base
    # executor's value when this column is unset), not "no requirement at
    # all" - an admin who wants to explicitly lift a requirement must still
    # set this column, there is no separate sentinel for that today.
    required_connector_type_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    default_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Optionally narrows/relabels fields from the base executor's JSON
    # schema (e.g. hiding "action" behind a friendly pre-filled label) -
    # shallow-merged over the base schema by the palette endpoint, never
    # mutating the base executor's own schema.
    config_schema_overrides: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class WorkflowStarterTemplate(Base, TimestampMixin):
    """Admin-managed, ready-to-use example workflow a tenant can start a new
    workflow from (composable-workflow-builder redesign, Phase 6) - the
    proof that the new composable node types (`whatsapp.ask_choice`,
    `flow.confirm`, `records.query`/`records.upsert`, `payments.send_razorpay_link`,
    ...) can actually assemble a real guided flow, not just exist in
    isolation. Global/platform-managed, not tenant-scoped - same pattern as
    `WorkflowNodeTemplate`/`BusinessTemplate`: every tenant sees the same
    active templates, and starting from one is a one-time copy (see
    `workflows.service.create_workflow_from_starter_template`), not a live
    link - editing the resulting workflow never touches this row.

    `graph_json` is a full authored `{"nodes": [...], "edges": [...]}`
    graph built entirely from real, registered node types (see
    `scripts/seed_workflow_starter_templates.py`) - nothing about a
    template's graph is special-cased at execution time; it publishes and
    runs exactly like a hand-built graph, and every node in it can be
    freely edited, removed, or added to afterward.

    `required_object_types`, when set, lists the tenant-defined "custom
    business object" types (see `modules.business_objects`) this template's
    graph assumes exist (e.g. an "Appointment" object for a booking flow) -
    each spec shaped `{"key", "name", "icon"?, "fields": [{"key", "label",
    "field_type", "options"?, "required"?, "sort_order"?}, ...]}`.
    `create_workflow_from_starter_template` auto-provisions any of these
    the tenant doesn't already have (by `key`) before seeding the graph, so
    picking this template "just works" with zero manual setup - but never
    overwrites/upgrades one the tenant already has under that key (a
    deliberately simple idempotency rule, not a merge/migration mechanism -
    see that function's docstring).
    """

    __tablename__ = "workflow_starter_templates"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="General")
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    graph_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    required_object_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Free-text admin guidance for anything a tenant should do before using
    # this template that ISN'T a connector dependency or a
    # `required_object_types` entry (e.g. "populate your product catalog
    # first") - optional, purely informational, never validated.
    setup_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class WorkflowComponent(Base, TimestampMixin):
    """Admin-managed, ready-to-use *fragment* of a workflow - a handful of
    nodes+edges (e.g. "ask for a coupon code, validate it, branch") a
    tenant inserts into a workflow they're already editing, as opposed to
    `WorkflowStarterTemplate`'s whole-new-workflow shape. Global/platform-
    managed, same pattern as that table - every tenant sees the same
    active components. See `modules.workflows.models.WorkflowUserComponent`
    for the tenant-saved-their-own-selection sibling of this table; both
    are merged into one list by `workflows.service.list_components`.

    `graph_fragment` is a `{"nodes": [...], "edges": [...]}` fragment, the
    same React-Flow JSON shape a full workflow graph uses - deliberately
    small and usually left with some wiring dangling on purpose (e.g. a
    `flow.confirm`'s "no" handle unwired, or a node referencing a
    placeholder token like `"{{YOUR_ORDER_NODE_ID.order_id}}"`) for the
    author to wire into their own workflow after inserting it - the exact
    same "placeholder the author fills in" mental model
    `WorkflowStarterTemplate`'s placeholder `connector_instance_id`s
    already use, so no new validation concept is needed: the existing
    unconnected-handle canvas styling and publish-time validation panel
    already surface exactly what's still dangling.

    `required_object_types` - same shape/semantics as
    `WorkflowStarterTemplate.required_object_types` - is auto-provisioned
    for the tenant (see `workflows.service.provision_required_object_types`)
    before a component is inserted, in case its nodes reference a custom
    business object (e.g. the "Post-Purchase Rating Request" component
    needs a "feedback" object type).
    """

    __tablename__ = "workflow_components"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="General")
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    graph_fragment: Mapped[dict] = mapped_column(JSONB, nullable=False)
    required_object_types: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Same purpose as `WorkflowStarterTemplate.setup_notes` - optional,
    # informational-only prerequisite guidance for this fragment.
    setup_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
