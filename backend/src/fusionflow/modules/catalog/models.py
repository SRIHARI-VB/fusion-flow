"""Catalog models: products/services, coupons, offers.

All three are tenant-scoped (`TenantScopedMixin` -> RLS) and each carries a
`custom_fields JSONB` column validated at write time against the tenant's
`custom_fields.models.FieldDefinition` rows (see
`modules/catalog/service.py::validate_entity_custom_fields`) - one JSONB
column per base table rather than a generic EAV table, per the plan's data
model rationale (better query performance, matches "JSONB-backed fields on
a base template" directly).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class ProductServiceType(str, enum.Enum):
    """Narrower than `custom_fields.models.EntityType` on purpose - `products_services`
    never holds a coupon/offer row - but shares the same string values, so
    `EntityType(ProductServiceType.PRODUCT.value)` always round-trips."""

    PRODUCT = "product"
    SERVICE = "service"


class DiscountType(str, enum.Enum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


class ProductService(Base, TenantScopedMixin, TimestampMixin):
    """A tenant's sellable product or service.

    One table for both `product` and `service` rows (see
    `modules/catalog/router.py` for why the two are still exposed as
    separate `/products` and `/services` routers): the two entity kinds
    share an identical shape in phase 1, differing only in the
    `entity_type` discriminator and which custom-field template applies.
    """

    __tablename__ = "products_services"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entity_type: Mapped[ProductServiceType] = mapped_column(
        Enum(ProductServiceType, name="product_service_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    base_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Coupon(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "coupons"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_coupon_tenant_code"),)

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    discount_type: Mapped[DiscountType] = mapped_column(
        Enum(DiscountType, name="coupon_discount_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    discount_value: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Free-form description of what the coupon applies to (product/service ids,
    # categories, "all" ...) - JSONB rather than a join table, matching the
    # same "shape still fluid in phase 1" rationale as custom_fields.
    applies_to: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)


class Offer(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "offers"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Free-form description of what the offer applies to (product/service ids,
    # categories, "all" ...) - JSONB rather than a join table, matching the
    # same "shape still fluid in phase 1" rationale as custom_fields.
    applies_to: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    # Unlike Coupon's discount_type/discount_value (always required - a
    # coupon *is* a discount), an offer's promotional value is optional:
    # a qualitative offer ("free consultation with any treatment") has no
    # percentage/amount to show, so both columns are nullable rather than
    # forcing a fake number.
    discount_type: Mapped[DiscountType | None] = mapped_column(
        Enum(DiscountType, name="coupon_discount_type", values_callable=lambda e: [m.value for m in e]),
        nullable=True,
    )
    discount_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    active_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
