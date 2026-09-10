"""Payment domain logic.

None of these functions commit — routers own the transaction boundary.
Queries filter explicitly on `tenant_id` as defense-in-depth on top of RLS
(see `modules/customers/service.py` for the same convention).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.payments.models import Payment, PaymentStatus
from fusionflow.modules.payments.schemas import PaymentCreate


async def list_payments(session: AsyncSession, tenant_id: uuid.UUID) -> list[Payment]:
    rows = await session.execute(
        select(Payment).where(Payment.tenant_id == tenant_id).order_by(Payment.created_at.desc())
    )
    return list(rows.scalars().all())


async def get_payment(session: AsyncSession, tenant_id: uuid.UUID, payment_id: uuid.UUID) -> Payment | None:
    return (
        await session.execute(
            select(Payment).where(Payment.id == payment_id, Payment.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def create_payment(session: AsyncSession, tenant_id: uuid.UUID, payload: PaymentCreate) -> Payment:
    payment = Payment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        order_id=payload.order_id,
        customer_id=payload.customer_id,
        connector_instance_id=payload.connector_instance_id,
        provider_ref=payload.provider_ref,
        amount=payload.amount,
        currency=payload.currency,
        status=payload.status,
        raw_event_ref=payload.raw_event_ref,
    )
    session.add(payment)
    await session.flush()
    return payment


async def get_payment_by_provider_ref(
    session: AsyncSession, tenant_id: uuid.UUID, provider_ref: str
) -> Payment | None:
    return (
        await session.execute(
            select(Payment).where(Payment.tenant_id == tenant_id, Payment.provider_ref == provider_ref)
        )
    ).scalar_one_or_none()


async def upsert_payment_from_provider(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connector_instance_id: uuid.UUID,
    provider_ref: str,
    amount: Decimal,
    currency: str,
    status: PaymentStatus,
    customer_id: uuid.UUID | None = None,
    order_id: uuid.UUID | None = None,
    raw_event_ref: str | None = None,
) -> Payment:
    """Create-or-update a `Payment` row from an inbound provider webhook.

    Keyed on `(tenant_id, provider_ref)` (the provider's own payment id) so
    a redelivered webhook - Razorpay, like most providers, retries on
    anything but a fast 2xx - updates the existing row (e.g.
    `captured` arriving after an earlier `pending`) instead of creating a
    duplicate. `customer_id`/`order_id` stay whatever they already were on
    update if the new event doesn't supply them, since a later status
    update (e.g. `refunded`) usually carries less context than the
    original `captured` event did.
    """
    existing = await get_payment_by_provider_ref(session, tenant_id, provider_ref)
    if existing is not None:
        existing.status = status
        existing.amount = amount
        existing.currency = currency
        if customer_id is not None:
            existing.customer_id = customer_id
        if order_id is not None:
            existing.order_id = order_id
        if raw_event_ref is not None:
            existing.raw_event_ref = raw_event_ref
        await session.flush()
        return existing

    payment = Payment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        order_id=order_id,
        customer_id=customer_id,
        connector_instance_id=connector_instance_id,
        provider_ref=provider_ref,
        amount=amount,
        currency=currency,
        status=status,
        raw_event_ref=raw_event_ref,
    )
    session.add(payment)
    await session.flush()
    return payment
