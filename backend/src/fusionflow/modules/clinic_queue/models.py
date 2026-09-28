"""`PatientVisit` — the "Patient Flow" Kanban module's single lifecycle
row (Reception -> With Doctor -> Billing -> Completed).

A first-class module, not a `business_objects` custom type: this needs a
real user-reference column (`assigned_doctor_membership_id`), a real
ordering column (`position`), and atomic per-transition field validation
(enforced in `service.py`) that the generic `ObjectRecord`/JSONB-payload
system has no way to express - confirmed by re-reading
`business_objects/models.py` before building this, not assumed.

One row per visit covers the whole lifecycle (not one row per stage) -
the same row that started in `reception` is the row that ends up
`completed`, just with more fields filled in as it moves. This makes the
history table trivial (`WHERE stage = 'completed'`) instead of needing a
join across per-stage tables.

`appointment_ref_id` is a plain UUID, deliberately NOT a real FK - it
points at an `object_records.id` row (the `appointment` custom object
type lives in `business_objects`, a different module), matching this
codebase's established cross-module-reference convention (see
`WorkflowTrigger.connector_instance_id`'s docstring for the same
reasoning): a real FK would force this module to depend on
`business_objects`'s table existing in exactly this shape forever.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class PatientVisitStage(str, enum.Enum):
    RECEPTION = "reception"
    WITH_DOCTOR = "with_doctor"
    BILLING = "billing"
    COMPLETED = "completed"


class PaymentMode(str, enum.Enum):
    CASH = "cash"
    CARD = "card"
    UPI = "upi"
    INSURANCE = "insurance"
    OTHER = "other"


class PatientVisit(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "patient_visits"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Not a real FK - see module docstring.
    appointment_ref_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    assigned_doctor_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("memberships.id", ondelete="SET NULL"), nullable=True, index=True
    )
    stage: Mapped[PatientVisitStage] = mapped_column(
        Enum(PatientVisitStage, name="patient_visit_stage", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=PatientVisitStage.RECEPTION,
        server_default=PatientVisitStage.RECEPTION.value,
        index=True,
    )
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    doctor_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consultation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount_to_collect: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    billing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_mode: Mapped[PaymentMode | None] = mapped_column(
        Enum(PaymentMode, name="patient_visit_payment_mode", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    amount_collected: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    # Ordering within the current stage's column - append-at-end (max+1) for
    # v1; a drag-to-reorder-within-column endpoint is a natural v2 addition
    # on top of this column, not a schema change.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
