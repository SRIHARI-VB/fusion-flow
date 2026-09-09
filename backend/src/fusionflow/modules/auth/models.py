"""Auth models: users and refresh tokens.

Both are *platform-level* tables and are deliberately NOT tenant-scoped:
one user can belong to several businesses, and both tables are read during
login/refresh - before any tenant context exists - so neither can carry a
`tenant_id` or an RLS policy.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fusionflow.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    """A platform identity. Not tenant-scoped - see module docstring."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    # argon2id hash produced by core.security.hash_password. Never selected
    # into any response schema.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    memberships: Mapped[list["Membership"]] = relationship(  # noqa: F821
        back_populates="user", cascade="all, delete-orphan"
    )
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class RefreshToken(Base):
    """One issued refresh token.

    Only the sha256 hex digest of the opaque token is stored, so a DB dump
    cannot be replayed as a session. Rotation chains rows via
    `replaced_by_id`; every chain shares one `family_id`. Presenting an
    already-rotated (i.e. `revoked_at IS NOT NULL`) token is treated as
    theft and revokes the whole family - see auth.service.refresh_tokens.
    """

    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    # Shared by every token in one rotation chain; the unit of revocation
    # when reuse is detected.
    family_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)
    # NULL for a pre-tenant (identity-only) session that has not yet
    # selected a business.
    business_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("refresh_tokens.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    @property
    def is_active(self) -> bool:
        from datetime import timezone

        return self.revoked_at is None and self.expires_at > datetime.now(timezone.utc)
