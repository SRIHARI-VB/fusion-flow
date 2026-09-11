"""`ModuleQueryAdapter` registration for `customers` - full CRUD, no
deliberate exceptions (unlike Payments/Orders - see the Phase 6 plan)."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.customers import service as customers_service
from fusionflow.modules.customers.schemas import CustomerCreate, CustomerOut, CustomerUpdate
from fusionflow.modules.workflows.engine.module_registry import ModuleQueryAdapter, registry


class CustomersQueryAdapter(ModuleQueryAdapter):
    module_key = "customers"

    async def list(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        items = await customers_service.list_customers(
            session,
            tenant_id,
            name_search=filters.get("name_search"),
            email=filters.get("email"),
            phone=filters.get("phone"),
            external_ref=filters.get("external_ref"),
            limit=limit,
        )
        return [CustomerOut.model_validate(item).model_dump(mode="json") for item in items]

    async def get(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> dict[str, Any] | None:
        item = await customers_service.get_customer(session, tenant_id, item_id)
        return CustomerOut.model_validate(item).model_dump(mode="json") if item else None

    async def create(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any]:
        payload = CustomerCreate.model_validate(fields)
        item = await customers_service.create_customer(session, tenant_id, payload)
        return CustomerOut.model_validate(item).model_dump(mode="json")

    async def update(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        item = await customers_service.get_customer(session, tenant_id, item_id)
        if item is None:
            return None
        payload = CustomerUpdate.model_validate(fields)
        updated = await customers_service.update_customer(session, item, payload)
        return CustomerOut.model_validate(updated).model_dump(mode="json")


registry.register(CustomersQueryAdapter())
