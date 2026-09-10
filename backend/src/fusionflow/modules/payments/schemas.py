from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.payments.models import PaymentStatus


class PaymentCreate(BaseModel):
    """Manual/test creation only.

    Production payments arrive via connector webhooks in a later wave
    (M4 Razorpay adapter) — this endpoint exists so the payment record
    shape can be exercised end-to-end before that adapter lands.
    """

    order_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    connector_instance_id: uuid.UUID | None = None
    provider_ref: str | None = Field(default=None, max_length=200)
    amount: Decimal = Field(ge=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    status: PaymentStatus = PaymentStatus.PENDING
    raw_event_ref: str | None = Field(default=None, max_length=500)


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    connector_instance_id: uuid.UUID | None
    provider_ref: str | None
    amount: Decimal
    currency: str
    status: PaymentStatus
    raw_event_ref: str | None
    created_at: datetime
