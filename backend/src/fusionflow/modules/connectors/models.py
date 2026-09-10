"""Connector framework models: the generic lifecycle tables used by every
connector, present and future (WhatsApp/Razorpay in phase 1).

Per the plan's "Connector Lifecycle Framework" section, everything here is
provider-agnostic - `connector_types` is the catalog a provider adapter
registers itself against by `key`; `connector_instances` is the per-tenant
row tracking the fixed state machine; `connector_credentials` holds only
ciphertext (never selected into a response DTO - see
`fusionflow.modules.connectors.schemas`); `connector_events` is the
audit/health trail; `connector_oauth_states` correlates an OAuth callback
back to the tenant/instance that started it.

RLS note: `connector_types` is a **global catalog** (like
`field_templates`), not tenant data, so it is deliberately NOT
`TenantScopedMixin` - every other table here is tenant-scoped and needs a
`fusionflow.db.rls.enable_tenant_rls(op, "<table>")` call in its eventual
migration (not added yet - models only, per this wave's scope).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class ConnectorCategory(str, enum.Enum):
    MESSAGING = "messaging"
    PAYMENT = "payment"
    CALENDAR = "calendar"
    MAIL = "mail"
    SUPPORT_AGENT = "support_agent"
    DASHBOARD = "dashboard"
    # Internal fixed feature module (products, orders, tickets, ...) - no
    # adapter, no OAuth, no ConnectorInstance state machine. Entitlement
    # alone (get_connector_access_map == "granted") gates its routes; see
    # modules.connectors.deps.require_module_access.
    FEATURE = "feature"


class ConnectorState(str, enum.Enum):
    """Fixed lifecycle state machine (plan: "Connector Lifecycle Framework").

    not_connected -> connecting -> connected -> action_required -> error
    -> disconnected, with error/action_required able to loop back to
    connecting via reconnect. Enforced in `service.py`, not by a DB
    constraint (the set of legal transitions is app-level policy).
    """

    NOT_CONNECTED = "not_connected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ACTION_REQUIRED = "action_required"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class HealthStatus(str, enum.Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class ConnectorEventType(str, enum.Enum):
    WEBHOOK_RECEIVED = "webhook_received"
    SYNC = "sync"
    OAUTH_CALLBACK = "oauth_callback"
    ERROR = "error"


class ConnectorAccessRequestStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class ConnectorType(Base, TimestampMixin):
    """Global connector catalog - one row per provider adapter.

    Not tenant-scoped: every business sees the same catalog. Seeded by
    application code (or a future admin-managed template), not per-tenant
    writes. `key` is what `ConnectorRegistry` (base.py) is keyed on.
    """

    __tablename__ = "connector_types"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    category: Mapped[ConnectorCategory] = mapped_column(
        Enum(ConnectorCategory, name="connector_category", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    config_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    oauth: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_enabled_globally: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    instances: Mapped[list["ConnectorInstance"]] = relationship(back_populates="connector_type")


class ConnectorInstance(Base, TenantScopedMixin, TimestampMixin):
    """One tenant's connection to one provider (e.g. "this business's WhatsApp number")."""

    __tablename__ = "connector_instances"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    state: Mapped[ConnectorState] = mapped_column(
        Enum(ConnectorState, name="connector_state", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=ConnectorState.NOT_CONNECTED,
        server_default=ConnectorState.NOT_CONNECTED.value,
    )
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Safe-field allowlist only (e.g. WABA display phone number, Razorpay
    # merchant id) - populated exclusively by adapter code, never raw
    # provider payloads. See base.ConnectorAdapter docstring.
    connected_identity: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    health_status: Mapped[HealthStatus | None] = mapped_column(
        Enum(HealthStatus, name="connector_health_status", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Retained permanently after disconnect (plan: "for support") - never
    # cleared by disconnect, unlike connected_identity/health which a
    # reconnect will refresh.
    provider_ref_ids: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    connector_type: Mapped[ConnectorType] = relationship(back_populates="instances")
    credentials: Mapped[list["ConnectorCredential"]] = relationship(
        back_populates="connector_instance", cascade="all, delete-orphan"
    )
    events: Mapped[list["ConnectorEvent"]] = relationship(
        back_populates="connector_instance", cascade="all, delete-orphan"
    )


class ConnectorCredential(Base, TenantScopedMixin):
    """Encrypted secret material for one connector instance.

    Exactly one active row per instance in phase 1 - rotation overwrites
    `ciphertext`/`redacted_preview` in place and stamps `rotated_at`
    rather than inserting a new row, matching the field shape called for
    in the plan. `ciphertext` is a Fernet token (see
    `fusionflow.core.encryption`) over a small JSON blob so multi-field
    secrets (e.g. Razorpay's key_id + key_secret + webhook_secret) fit in
    one column. **Never** add this model to a Pydantic response schema.
    """

    __tablename__ = "connector_credentials"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_instance_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("connector_instances.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_version: Mapped[int] = mapped_column(Integer, nullable=False)
    redacted_preview: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    connector_instance: Mapped[ConnectorInstance] = relationship(back_populates="credentials")


class ConnectorEvent(Base, TenantScopedMixin):
    """Audit/health trail row - one per webhook delivery, sync, OAuth callback, or error."""

    __tablename__ = "connector_events"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_instance_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_type: Mapped[ConnectorEventType] = mapped_column(
        Enum(ConnectorEventType, name="connector_event_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    connector_instance: Mapped[ConnectorInstance] = relationship(back_populates="events")


class ConnectorOAuthState(Base, TenantScopedMixin):
    """Short-lived CSRF-safe state for correlating an OAuth callback.

    `connector_instance_id` is nullable because the instance may not
    exist yet the first time a tenant starts a brand-new OAuth connect
    (vs. a reconnect of an existing `error`/`action_required` instance).
    """

    __tablename__ = "connector_oauth_states"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=True, index=True
    )
    state_token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    redirect_context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConnectorAccessRequest(Base, TenantScopedMixin):
    """A tenant's request for access to a connector type outside its
    `business_template`'s bundle.

    Genuinely per-tenant (unlike every other new table this task adds -
    see `modules.admin.models`'s module docstring), so this is the one
    table in the whole "business templates / plans / entitlements" feature
    that gets `TenantScopedMixin` and RLS. `modules.connectors.service.connect()`
    treats an `approved` row here as the second of the two ways a tenant is
    entitled to connect a given `connector_type_id` (the first being
    membership in its `business_template`'s bundle via
    `modules.admin.models.BusinessTemplateConnectorType`).

    Admin routes reviewing this table (`/api/admin/connector-access-requests/*`)
    have no `app.current_tenant_id` by default - see this task's report on
    how `modules.admin.service` resolves the owning tenant before mutating.
    """

    __tablename__ = "connector_access_requests"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_types.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    status: Mapped[ConnectorAccessRequestStatus] = mapped_column(
        Enum(
            ConnectorAccessRequestStatus,
            name="connector_access_request_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=ConnectorAccessRequestStatus.PENDING,
        server_default=ConnectorAccessRequestStatus.PENDING.value,
        index=True,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    connector_type: Mapped["ConnectorType"] = relationship()


class ConnectorAccessOverride(Base, TenantScopedMixin, TimestampMixin):
    """An admin's explicit revoke/grant for ONE tenant on ONE connector or
    fixed module, independent of `business_template` bundle membership or
    any `ConnectorAccessRequest`.

    Without this table there was no way to revoke a single bundled item
    from one tenant without either reassigning its whole template (losing
    every other grant it gives) or unassigning the template entirely -
    which, for FEATURE-category modules, actually *over*-grants via the
    grandfathering compat branch in `modules.connectors.deps` (a
    pre-template tenant with no `business_template_id` gets full access).
    `get_connector_access_map` checks this table FIRST, before the
    bundle/request resolution - a row here always wins until an admin
    deletes it (`DELETE /admin/tenants/{id}/connectors/{key}/override`),
    reverting to the normal resolution.
    """

    __tablename__ = "connector_access_overrides"
    __table_args__ = (
        UniqueConstraint("tenant_id", "connector_type_id", name="uq_connector_access_override_tenant_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_type_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_types.id", ondelete="CASCADE"), nullable=False, index=True
    )
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    set_by: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    connector_type: Mapped["ConnectorType"] = relationship()
