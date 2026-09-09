"""Payment domain logic.

None of these functions commit — routers own the transaction boundary.
Queries filter explicitly on `tenant_id` as defense-in-depth on top of RLS
(see `modules/customers/service.py` for the same convention).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.payments.models import Payment
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
