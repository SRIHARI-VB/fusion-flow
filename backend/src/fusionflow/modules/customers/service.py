"""Customer domain logic.

None of these functions commit — routers own the transaction boundary (see
`modules/auth/service.py` for the same convention).

Every query filters explicitly on `tenant_id` in addition to relying on
Postgres RLS (`SET LOCAL app.current_tenant_id`, applied by
`get_tenant_context`). The explicit filter is defense-in-depth, not the
primary isolation mechanism — see the plan's Risk #2 on `SET LOCAL`.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.customers.models import Customer
from fusionflow.modules.customers.schemas import CustomerCreate, CustomerUpdate


async def list_customers(session: AsyncSession, tenant_id: uuid.UUID) -> list[Customer]:
    rows = await session.execute(
        select(Customer).where(Customer.tenant_id == tenant_id).order_by(Customer.created_at.desc())
    )
    return list(rows.scalars().all())


async def get_customer(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> Customer | None:
    return (
        await session.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def create_customer(
    session: AsyncSession, tenant_id: uuid.UUID, payload: CustomerCreate
) -> Customer:
    customer = Customer(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        external_ref=payload.external_ref,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        custom_fields=payload.custom_fields,
    )
    session.add(customer)
    await session.flush()
    return customer


async def update_customer(
    session: AsyncSession, customer: Customer, payload: CustomerUpdate
) -> Customer:
    """Apply a partial update in place. Does not commit."""
    if payload.external_ref is not None:
        customer.external_ref = payload.external_ref
    if payload.name is not None:
        customer.name = payload.name
    if payload.email is not None:
        customer.email = payload.email
    if payload.phone is not None:
        customer.phone = payload.phone
    if payload.custom_fields is not None:
        customer.custom_fields = payload.custom_fields
    await session.flush()
    return customer


async def delete_customer(session: AsyncSession, customer: Customer) -> None:
    await session.delete(customer)
    await session.flush()
