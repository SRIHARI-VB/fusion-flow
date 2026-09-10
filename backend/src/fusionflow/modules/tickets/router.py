"""`/api/v1/tickets` (+ `/tickets/{id}/messages`) — the fixed connector (M2).

Not mounted here — see `api.py`'s docstring; the integration wave mounts
`router` from this module under the `/api/v1` group.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.tickets import service as tickets_service
from fusionflow.modules.tickets.schemas import (
    TicketCreate,
    TicketMessageCreate,
    TicketMessageOut,
    TicketOut,
    TicketUpdate,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("", response_model=list[TicketOut])
async def list_tickets(session: SessionDep, context: TenantContextDep) -> list[TicketOut]:
    return await tickets_service.list_tickets(session, context.tenant_id)


@router.post("", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate, session: SessionDep, context: TenantContextDep
) -> TicketOut:
    ticket = await tickets_service.create_ticket(session, context.tenant_id, payload)
    await commit_and_keep_tenant_context(session)
    await session.refresh(ticket)
    out = await tickets_service.get_ticket_out(session, context.tenant_id, ticket.id)
    assert out is not None
    return out


@router.get("/{ticket_id}", response_model=TicketOut)
async def get_ticket(ticket_id: uuid.UUID, session: SessionDep, context: TenantContextDep) -> TicketOut:
    ticket = await tickets_service.get_ticket_out(session, context.tenant_id, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: TicketUpdate,
    session: SessionDep,
    context: TenantContextDep,
) -> TicketOut:
    ticket = await tickets_service.get_ticket(session, context.tenant_id, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    await tickets_service.update_ticket(session, ticket, payload)
    await commit_and_keep_tenant_context(session)
    out = await tickets_service.get_ticket_out(session, context.tenant_id, ticket_id)
    assert out is not None
    return out


@router.get("/{ticket_id}/messages", response_model=list[TicketMessageOut])
async def list_ticket_messages(
    ticket_id: uuid.UUID, session: SessionDep, context: TenantContextDep
) -> list[TicketMessageOut]:
    ticket = await tickets_service.get_ticket(session, context.tenant_id, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    messages = await tickets_service.list_messages(session, context.tenant_id, ticket_id)
    return [TicketMessageOut.model_validate(message) for message in messages]


@router.post(
    "/{ticket_id}/messages", response_model=TicketMessageOut, status_code=status.HTTP_201_CREATED
)
async def add_ticket_message(
    ticket_id: uuid.UUID,
    payload: TicketMessageCreate,
    session: SessionDep,
    context: TenantContextDep,
) -> TicketMessageOut:
    ticket = await tickets_service.get_ticket(session, context.tenant_id, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    message = await tickets_service.add_message(session, context.tenant_id, ticket_id, payload)
    await commit_and_keep_tenant_context(session)
    await session.refresh(message)
    return TicketMessageOut.model_validate(message)
