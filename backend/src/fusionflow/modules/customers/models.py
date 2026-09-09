"""Customer model — the first of the five fixed connectors (M2).

`Customer` is tenant-scoped (`TenantScopedMixin`) but deliberately has no
`updated_at`: the plan's field list for this table is `id, tenant_id,
external_ref, name, email, phone, custom_fields, created_at` only, so this
matches that spec exactly rather than defaulting to `TimestampMixin`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin


class Customer(Base, TenantScopedMixin):
    """A tenant's end customer.

    `external_ref` is the tenant's own identifier for this customer (e.g.
    an id carried over from a system they migrated from), kept distinct
    from our `id` so imports/upserts can be idempotent on it. `custom_fields`
    is validated against `field_definitions` at write time by the
    custom-fields module (a different Wave 1 agent); this module does not
    itself enforce that schema, it only stores whatever JSON it is given.
    """

    __tablename__ = "customers"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_ref: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
