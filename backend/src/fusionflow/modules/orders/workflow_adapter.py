"""`ModuleQueryAdapter` registration for `orders` - **no create node**
(orders originate from checkout, not workflow-authorship) and `update` is
restricted to `status` only (rewriting `total_amount`/`line_items` from a
workflow would be a data-integrity hazard) - both deliberate, called-out
exceptions from the Phase 6 plan, not CRUD applied mechanically.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.orders import service as orders_service
from fusionflow.modules.orders.models import OrderStatus
from fusionflow.modules.orders.schemas import OrderOut, OrderUpdate
from fusionflow.modules.workflows.engine.module_registry import ModuleQueryAdapter, registry


class OrdersQueryAdapter(ModuleQueryAdapter):
    module_key = "orders"

    async def list(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        status_value = filters.get("status")
        customer_id = filters.get("customer_id")
        items = await orders_service.list_orders(
            session,
            tenant_id,
            status=OrderStatus(status_value) if status_value else None,
            customer_id=uuid.UUID(customer_id) if customer_id else None,
            limit=limit,
        )
        return [item.model_dump(mode="json") for item in items]

    async def get(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> dict[str, Any] | None:
        item = await orders_service.get_order_out(session, tenant_id, item_id)
        return item.model_dump(mode="json") if item else None

    async def update(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        extra_fields = set(fields) - {"status"}
        if extra_fields:
            raise ValueError(
                f"module.update on 'orders' only supports the 'status' field - got {sorted(extra_fields)}"
            )
        order = await orders_service.get_order(session, tenant_id, item_id)
        if order is None:
            return None
        payload = OrderUpdate.model_validate(fields)
        await orders_service.update_order(session, order, payload)
        updated = await orders_service.get_order_out(session, tenant_id, item_id)
        return updated.model_dump(mode="json") if updated else None


registry.register(OrdersQueryAdapter())
