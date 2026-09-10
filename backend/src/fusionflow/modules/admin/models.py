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

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TimestampMixin


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
    """Catalog of platform feature flags (e.g. `support_agent_enabled`)."""

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
