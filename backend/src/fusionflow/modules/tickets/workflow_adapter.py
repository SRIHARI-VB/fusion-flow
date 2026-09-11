"""`ModuleQueryAdapter` registration for `tickets` - full CRUD."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.tickets import service as tickets_service
from fusionflow.modules.tickets.models import TicketStatus
from fusionflow.modules.tickets.schemas import TicketCreate, TicketUpdate
from fusionflow.modules.workflows.engine.module_registry import ModuleQueryAdapter, registry


class TicketsQueryAdapter(ModuleQueryAdapter):
    module_key = "tickets"

    async def list(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        status_value = filters.get("status")
        customer_id = filters.get("customer_id")
        assigned_user_id = filters.get("assigned_user_id")
        items = await tickets_service.list_tickets(
            session,
            tenant_id,
            status=TicketStatus(status_value) if status_value else None,
            priority=filters.get("priority"),
            assigned_user_id=uuid.UUID(assigned_user_id) if assigned_user_id else None,
            customer_id=uuid.UUID(customer_id) if customer_id else None,
            limit=limit,
        )
        return [item.model_dump(mode="json") for item in items]

    async def get(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> dict[str, Any] | None:
        item = await tickets_service.get_ticket_out(session, tenant_id, item_id)
        return item.model_dump(mode="json") if item else None

    async def create(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any]:
        payload = TicketCreate.model_validate(fields)
        ticket = await tickets_service.create_ticket(session, tenant_id, payload)
        created = await tickets_service.get_ticket_out(session, tenant_id, ticket.id)
        assert created is not None
        return created.model_dump(mode="json")

    async def update(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        ticket = await tickets_service.get_ticket(session, tenant_id, item_id)
        if ticket is None:
            return None
        payload = TicketUpdate.model_validate(fields)
        await tickets_service.update_ticket(session, ticket, payload)
        updated = await tickets_service.get_ticket_out(session, tenant_id, item_id)
        return updated.model_dump(mode="json") if updated else None


registry.register(TicketsQueryAdapter())
