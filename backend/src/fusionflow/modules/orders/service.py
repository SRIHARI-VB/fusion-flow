"""Order domain logic.

None of these functions commit — routers own the transaction boundary.
Queries filter explicitly on `tenant_id` as defense-in-depth on top of RLS
(see `modules/customers/service.py` for the same convention).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.customers.models import Customer
from fusionflow.modules.orders.models import Order
from fusionflow.modules.orders.schemas import OrderCreate, OrderOut, OrderUpdate
from fusionflow.modules.workflows.engine import event_bus


def to_order_out(order: Order, customer_name: str | None = None) -> OrderOut:
    return OrderOut(
        id=order.id,
        customer_id=order.customer_id,
        customer_name=customer_name,
        status=order.status,
        total_amount=order.total_amount,
        currency=order.currency,
        line_items=order.line_items,
        created_at=order.created_at,
        updated_at=order.updated_at,
    )


async def list_orders(session: AsyncSession, tenant_id: uuid.UUID) -> list[OrderOut]:
    rows = await session.execute(
        select(Order, Customer.name)
        .join(Customer, Customer.id == Order.customer_id)
        .where(Order.tenant_id == tenant_id)
        .order_by(Order.created_at.desc())
    )
    return [to_order_out(order, customer_name) for order, customer_name in rows.all()]


async def get_order_out(session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID) -> OrderOut | None:
    row = (
        await session.execute(
            select(Order, Customer.name)
            .join(Customer, Customer.id == Order.customer_id)
            .where(Order.id == order_id, Order.tenant_id == tenant_id)
        )
    ).first()
    if row is None:
        return None
    order, customer_name = row
    return to_order_out(order, customer_name)


async def get_order(session: AsyncSession, tenant_id: uuid.UUID, order_id: uuid.UUID) -> Order | None:
    """Raw ORM instance, for handlers that need to mutate + flush (PATCH)."""
    return (
        await session.execute(select(Order).where(Order.id == order_id, Order.tenant_id == tenant_id))
    ).scalar_one_or_none()


async def create_order(session: AsyncSession, tenant_id: uuid.UUID, payload: OrderCreate) -> Order:
    order = Order(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        customer_id=payload.customer_id,
        status=payload.status,
        total_amount=payload.total_amount,
        currency=payload.currency,
        line_items=payload.line_items,
    )
    session.add(order)
    await session.flush()

    # Same transaction as the insert above - transactional outbox, see
    # event_bus.py's module docstring. The router owns the commit.
    await event_bus.publish_trigger_event(
        session,
        tenant_id=tenant_id,
        event_type="order.created",
        payload={
            "order_id": str(order.id),
            "customer_id": str(order.customer_id),
            "total_amount": str(order.total_amount),
            "currency": order.currency,
            "status": order.status.value,
        },
    )
    return order


async def update_order(session: AsyncSession, order: Order, payload: OrderUpdate) -> Order:
    if payload.status is not None:
        order.status = payload.status
    if payload.total_amount is not None:
        order.total_amount = payload.total_amount
    if payload.currency is not None:
        order.currency = payload.currency
    if payload.line_items is not None:
        order.line_items = payload.line_items
    await session.flush()
    return order
