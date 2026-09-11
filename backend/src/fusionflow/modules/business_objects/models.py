"""Custom Business Object module: lets a tenant define their own record
types (e.g. "Delivery", "Appointment") beyond the fixed catalog/orders/
customers modules, with tenant-scoped field definitions and generic
records - the escape hatch a composable workflow reaches for when it needs
a business concept this codebase doesn't model natively.

Deliberately NOT wired into `modules.workflows.engine.module_registry`'s
process-wide singleton at import time (see `workflow_adapter.py`'s module
docstring for why) - a workflow reaches a tenant's custom object type via
a per-request, per-tenant lookup instead.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin
from fusionflow.modules.custom_fields.models import FieldType

__all__ = ["FieldType", "ObjectFieldDefinition", "ObjectRecord", "ObjectTypeDefinition"]


class ObjectTypeDefinition(Base, TenantScopedMixin, TimestampMixin):
    """One tenant-defined business object type (e.g. "delivery",
    "appointment") - the module-picker entry a workflow author sees
    alongside the fixed modules (Products, Orders, ...), except this one
    the tenant created themselves, with whatever fields they need.
    """

    __tablename__ = "object_type_definitions"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_object_type_tenant_key"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class ObjectFieldDefinition(Base, TenantScopedMixin, TimestampMixin):
    """One field on a tenant's object type.

    Same shape/vocabulary as `custom_fields.models.FieldDefinition` (this
    module reuses its `FieldType` enum, and `service.validate_record_payload`
    reuses `custom_fields.validation.validate_custom_fields` directly,
    since both are duck-typed against `.key`/`.field_type`/`.required`/
    `.options`), but deliberately a separate table:
    `FieldDefinition.entity_type` is a closed, platform-fixed enum
    (product/service/coupon/offer) a tenant cannot extend, so a
    tenant-defined object type needs its own field-definition table, not a
    widened enum.
    """

    __tablename__ = "object_field_definitions"
    __table_args__ = (UniqueConstraint("object_type_id", "key", name="uq_object_field_type_key"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    object_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("object_type_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[FieldType] = mapped_column(
        Enum(
            FieldType,
            name="custom_field_type",
            values_callable=lambda e: [m.value for m in e],
            create_type=False,
        ),
        nullable=False,
    )
    options: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class ObjectRecord(Base, TenantScopedMixin, TimestampMixin):
    """One record of a tenant-defined object type - the generic "row" a
    workflow's `module.list`/`module.get`/`module.create`/`module.update`
    (via the runtime fallback added to those nodes) or the
    `/business-objects` REST API reads and writes.

    `customer_id` is a real, indexed FK rather than a JSONB field: "records
    for the customer in this conversation" is the dominant filter every
    conversational use case (delivery, appointment, ...) needs, so it earns
    a real column instead of a JSONB containment query.
    """

    __tablename__ = "object_records"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    object_type_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("object_type_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Traceability only ("which workflow run created this record") - no FK,
    # since workflow runs may be pruned independently of the records they
    # created.
    created_by_run_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
