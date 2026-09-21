"""Custom-fields models: global templates and per-tenant field definitions.

`FieldTemplate` is platform-seeded (see `backend/scripts/seed_templates.py`)
and read-only from the tenant's perspective; `POST
/custom-fields/templates/{id}/apply` copies its `fields` payload into the
tenant's own `FieldDefinition` rows (see service.apply_template) rather than
the tenant ever referencing the template live, so later template edits
never retroactively change what a tenant already applied (plan Risk #6:
field-definition edits are append-only-preferred).

`FieldDefinition` rows are the schema that `custom_fields.validation`
validates a catalog row's `custom_fields` JSONB payload against before
every write (see `modules/catalog/service.py::validate_entity_custom_fields`).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin


class EntityType(str, enum.Enum):
    """Shared across `field_templates`, `field_definitions` and the catalog tables.

    `products_services.entity_type` only ever takes PRODUCT/SERVICE (see
    `modules.catalog.models.ProductServiceType`, a narrower enum with the
    same string values) - reusing this enum end-to-end keeps
    `entity_type="product"` meaning exactly one thing across both modules.
    """

    PRODUCT = "product"
    SERVICE = "service"
    COUPON = "coupon"
    OFFER = "offer"


class FieldType(str, enum.Enum):
    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    SELECT = "select"
    MULTISELECT = "multiselect"
    DATE = "date"
    RICHTEXT = "richtext"


class ModuleFieldDefinitionMixin:
    """Shared column shape for a fixed module's own tenant-scoped field-definition table.

    `FieldDefinition` below is the older of two "custom fields" designs in
    this codebase: one shared table keyed by a closed, platform-fixed
    `EntityType` enum (product/service/coupon/offer only). Any other fixed
    module that wants tenant-defined custom fields (customers, tickets, ...)
    can't extend that enum, so it gets its own table instead — same column
    shape (mix this in), separate table. `business_objects.ObjectFieldDefinition`
    was the first of these; concrete per-module tables (e.g.
    `customers.CustomerFieldDefinition`) follow the same shape so
    `custom_fields.validation.validate_custom_fields` — duck-typed against
    `.key`/`.field_type`/`.required`/`.options` — validates all of them
    without caring which table a row came from.

    `create_type=False` on `field_type`: every subclass shares the single
    `custom_field_type` Postgres enum `FieldDefinition` defines below (created
    once, in migration 0003) rather than each table creating its own enum
    type.
    """

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


class FieldTemplate(Base):
    """A global, platform-seeded starter field set for one vertical + entity_type.

    Not tenant-scoped (no `TenantScopedMixin`/RLS): templates are shipped by
    the platform, not created by tenants, in phase 1.
    """

    __tablename__ = "field_templates"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    vertical: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, name="custom_field_entity_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    is_global: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    # [{"key", "label", "field_type", "options"?, "required"?, "sort_order"?}, ...]
    # - see custom_fields.schemas.FieldTemplateFieldSpec for the validated shape.
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class FieldDefinition(Base, TenantScopedMixin):
    """One tenant's custom-field metadata for one entity_type.

    `(tenant_id, entity_type, key)` is unique - a tenant cannot define the
    same field key twice for the same entity_type, whether it came from a
    template or was hand-created.
    """

    __tablename__ = "field_definitions"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "entity_type", "key", name="uq_field_definition_tenant_entity_key"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[EntityType] = mapped_column(
        Enum(EntityType, name="custom_field_entity_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    field_type: Mapped[FieldType] = mapped_column(
        Enum(FieldType, name="custom_field_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    options: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    source_template_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("field_templates.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
