import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model in the service."""


class TimestampMixin:
    """created_at / updated_at columns, maintained by the database.

    Always `timestamptz` (never naive) - every datetime that crosses the
    application boundary in this service is timezone-aware UTC, so token
    expiry comparisons and DB timestamps are directly comparable.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TenantScopedMixin:
    """Mixin for every tenant-scoped table.

    Adds the `tenant_id` column every RLS policy filters on (see
    db/rls.py::enable_tenant_rls). `businesses` lives in
    modules/tenancy/models.py; it is referenced here by table name only so
    this module never has to import modules/tenancy (avoids a circular
    import), matching SQLAlchemy's normal forward-reference pattern for
    cross-module foreign keys.
    """

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
