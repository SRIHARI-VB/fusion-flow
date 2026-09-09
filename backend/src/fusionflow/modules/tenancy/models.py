"""Tenancy models: businesses (tenants) and memberships (user <-> business).

Both are *platform-level* tables and are deliberately NOT tenant-RLS-scoped
(see the plan's "Core Data Model": platform tables such as users,
businesses, audit_log and feature_flags sit outside RLS). `businesses` is
itself the tenant registry - `TenantScopedMixin.tenant_id` points at
`businesses.id` - so it cannot filter on its own tenant_id. `memberships`
is read during login and business-switch, i.e. *before* any tenant context
exists, so it also stays outside RLS; it is protected in application code
by always filtering on the authenticated `user_id`.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fusionflow.db.base import Base, TimestampMixin


class MembershipRole(str, enum.Enum):
    """Role of a user within one business. Ordered most -> least privileged."""

    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class BusinessStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


class Business(Base, TimestampMixin):
    """A tenant. Every tenant-scoped table's `tenant_id` FKs to this table."""

    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    # Vertical drives which custom-field template set is seeded (Wave 1).
    vertical: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[BusinessStatus] = mapped_column(
        Enum(BusinessStatus, name="business_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=BusinessStatus.ACTIVE,
        server_default=BusinessStatus.ACTIVE.value,
    )
    onboarding_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )


class Membership(Base):
    """Join row granting one user a role in one business."""

    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("user_id", "business_id", name="uq_membership_user_business"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("businesses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, name="membership_role", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=MembershipRole.MEMBER,
    )
    invited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # NULL until the invitee accepts. Self-serve signup sets this immediately.
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    business: Mapped[Business] = relationship(back_populates="memberships")
    user: Mapped["User"] = relationship(back_populates="memberships")  # noqa: F821
