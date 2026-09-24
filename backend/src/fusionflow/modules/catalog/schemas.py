from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.catalog.models import DiscountType, ProductServiceType

# ---------------------------------------------------------------------------
# ProductService
# ---------------------------------------------------------------------------


class ProductServiceCreate(BaseModel):
    entity_type: ProductServiceType
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    base_price: Decimal = Field(default=Decimal("0"), ge=0)
    is_active: bool = True
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class ProductServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    base_price: Decimal | None = Field(default=None, ge=0)
    is_active: bool | None = None
    custom_fields: dict[str, Any] | None = None


class ProductServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    entity_type: ProductServiceType
    name: str
    description: str | None
    base_price: Decimal
    is_active: bool
    custom_fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Coupon
# ---------------------------------------------------------------------------


class CouponCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    discount_type: DiscountType
    discount_value: Decimal = Field(gt=0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=1)
    applies_to: dict[str, Any] = Field(default_factory=dict)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CouponUpdate(BaseModel):
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = Field(default=None, gt=0)
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=1)
    applies_to: dict[str, Any] | None = None
    custom_fields: dict[str, Any] | None = None


class CouponOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    discount_type: DiscountType
    discount_value: Decimal
    valid_from: datetime | None
    valid_to: datetime | None
    usage_limit: int | None
    applies_to: dict[str, Any]
    custom_fields: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Offer
# ---------------------------------------------------------------------------


class OfferCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = Field(default=None, gt=0)
    applies_to: dict[str, Any] = Field(default_factory=dict)
    custom_fields: dict[str, Any] = Field(default_factory=dict)
    active_from: datetime | None = None
    active_to: datetime | None = None


class OfferUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = Field(default=None, gt=0)
    applies_to: dict[str, Any] | None = None
    custom_fields: dict[str, Any] | None = None
    active_from: datetime | None = None
    active_to: datetime | None = None


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    discount_type: DiscountType | None
    discount_value: Decimal | None
    applies_to: dict[str, Any]
    custom_fields: dict[str, Any]
    active_from: datetime | None
    active_to: datetime | None
    created_at: datetime
    updated_at: datetime
