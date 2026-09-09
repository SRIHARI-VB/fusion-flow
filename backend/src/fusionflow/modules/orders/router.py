"""`/api/v1/orders` — the `orders` fixed connector (M2).

Not mounted here — see `api.py`'s docstring; the integration wave mounts
`router` from this module under the `/api/v1` group.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.modules.customers import service as customers_service
from fusionflow.modules.orders import service as orders_service
from fusionflow.modules.orders.schemas import OrderCreate, OrderOut, OrderUpdate

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
async def list_orders(session: SessionDep, context: TenantContextDep) -> list[OrderOut]:
    return await orders_service.list_orders(session, context.tenant_id)


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate, session: SessionDep, context: TenantContextDep
) -> OrderOut:
    customer = await customers_service.get_customer(session, context.tenant_id, payload.customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    order = await orders_service.create_order(session, context.tenant_id, payload)
    await session.commit()
    await session.refresh(order)
    return orders_service.to_order_out(order, customer.name)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: uuid.UUID, session: SessionDep, context: TenantContextDep) -> OrderOut:
    order = await orders_service.get_order_out(session, context.tenant_id, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order


@router.patch("/{order_id}", response_model=OrderOut)
async def update_order(
    order_id: uuid.UUID,
    payload: OrderUpdate,
    session: SessionDep,
    context: TenantContextDep,
) -> OrderOut:
    order = await orders_service.get_order(session, context.tenant_id, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    order = await orders_service.update_order(session, order, payload)
    await session.commit()
    await session.refresh(order)
    customer = await customers_service.get_customer(session, context.tenant_id, order.customer_id)
    return orders_service.to_order_out(order, customer.name if customer else None)
