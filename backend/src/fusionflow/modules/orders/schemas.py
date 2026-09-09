from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.orders.models import OrderStatus


class OrderCreate(BaseModel):
    customer_id: uuid.UUID
    status: OrderStatus = OrderStatus.PENDING
    total_amount: Decimal = Field(default=Decimal("0"), ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    line_items: list[dict[str, Any]] = Field(default_factory=list)


class OrderUpdate(BaseModel):
    """Partial update — every field optional, unset fields are left alone."""

    status: OrderStatus | None = None
    total_amount: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    line_items: list[dict[str, Any]] | None = None


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    # Denormalized for the list/detail views; populated by the service
    # layer's join, not stored on the `orders` row itself.
    customer_name: str | None = None
    status: OrderStatus
    total_amount: Decimal
    currency: str
    line_items: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
