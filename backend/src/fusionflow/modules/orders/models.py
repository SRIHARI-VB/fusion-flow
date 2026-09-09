"""Order model — the second fixed connector (M2).

`customer_id` is declared as a plain `ForeignKey("customers.id")` by table
name only (no `relationship()`, no import of `fusionflow.modules.customers`)
— the same pattern `TenantScopedMixin` uses for `businesses.id`, so
`orders` and `customers` stay independently importable and there is no risk
of a circular import between fixed-connector modules built in the same
wave. Service-layer code that needs the customer's name for a list view
does a plain `select().join()` instead of an ORM relationship (see
`service.py`).
"""

from __future__ import annotations

import enum
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import Enum, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class Order(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=OrderStatus.PENDING,
        server_default=OrderStatus.PENDING.value,
    )
    total_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"), server_default="0"
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD", server_default="USD")
    line_items: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
