"""Payment model — the third fixed connector (M2).

Payments are normally created by connector webhooks (M4 - Razorpay adapter,
a different Wave 1 agent), not by tenant users, so this module's router
keeps write routes minimal: only a `POST /payments` for manual/test
creation, no PATCH/DELETE.

`connector_instance_id` will eventually reference `connector_instances`
(owned by the connector-framework agent, running in this same parallel
wave). That table does not exist yet, so this column is deliberately a
plain nullable UUID with NO foreign key constraint — adding one now would
fail to migrate. The FK is added in the integration migration once the
connector framework lands.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin


class PaymentStatus(str, enum.Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(Base, TenantScopedMixin):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # FK to connector_instances.id, added in integration migration once connector framework lands
    connector_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True, index=True
    )
    provider_ref: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PaymentStatus.PENDING,
        server_default=PaymentStatus.PENDING.value,
    )
    # Pointer to the raw webhook payload/event this row was derived from
    # (e.g. a connector_events.id or storage key) — kept for support/replay,
    # not interpreted by this module.
    raw_event_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
