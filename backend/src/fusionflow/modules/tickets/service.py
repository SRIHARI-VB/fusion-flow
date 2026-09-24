"""Ticket + TicketMessage domain logic.

None of these functions commit — routers own the transaction boundary.
Queries filter explicitly on `tenant_id` as defense-in-depth on top of RLS
(see `modules/customers/service.py` for the same convention).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import registry as connector_registry
from fusionflow.modules.customers.models import Customer
from fusionflow.modules.tickets.models import Ticket, TicketMessage, TicketStatus
from fusionflow.modules.tickets.schemas import TicketCreate, TicketMessageCreate, TicketOut, TicketUpdate


def to_ticket_out(ticket: Ticket, customer_name: str | None = None) -> TicketOut:
    return TicketOut(
        id=ticket.id,
        customer_id=ticket.customer_id,
        customer_name=customer_name,
        subject=ticket.subject,
        status=ticket.status,
        priority=ticket.priority,
        source_connector_instance_id=ticket.source_connector_instance_id,
        assigned_user_id=ticket.assigned_user_id,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


async def list_tickets(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: TicketStatus | None = None,
    priority: str | None = None,
    assigned_user_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> list[TicketOut]:
    # outerjoin: `customer_id` is nullable (e.g. a ticket raised before the
    # customer record is matched), so an inner join would silently drop
    # those tickets from the list.
    stmt = (
        select(Ticket, Customer.name)
        .outerjoin(Customer, Customer.id == Ticket.customer_id)
        .where(Ticket.tenant_id == tenant_id)
    )
    if status is not None:
        stmt = stmt.where(Ticket.status == status)
    if priority is not None:
        stmt = stmt.where(Ticket.priority == priority)
    if assigned_user_id is not None:
        stmt = stmt.where(Ticket.assigned_user_id == assigned_user_id)
    if customer_id is not None:
        stmt = stmt.where(Ticket.customer_id == customer_id)
    # `id` as a secondary sort key: Postgres's `now()` is transaction-start
    # time, not per-statement time, so two tickets created back-to-back in
    # the same transaction can carry an identical `created_at` - without a
    # tie-breaker, "most recent first" becomes whatever order the scan
    # happens to return, not necessarily creation order. UUIDs aren't
    # naturally sortable-by-time, but a stable (if arbitrary) tie-break is
    # still strictly better than an unstable one for anything that treats
    # `list_tickets(..., limit=1)` as "the newest ticket" (see
    # `tickets.get_latest_for_customer`).
    stmt = stmt.order_by(Ticket.created_at.desc(), Ticket.id.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = await session.execute(stmt)
    return [to_ticket_out(ticket, customer_name) for ticket, customer_name in rows.all()]


async def get_ticket_out(session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> TicketOut | None:
    row = (
        await session.execute(
            select(Ticket, Customer.name)
            .outerjoin(Customer, Customer.id == Ticket.customer_id)
            .where(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id)
        )
    ).first()
    if row is None:
        return None
    ticket, customer_name = row
    return to_ticket_out(ticket, customer_name)


async def get_ticket(session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID) -> Ticket | None:
    """Raw ORM instance, for handlers that need to mutate + flush (PATCH)."""
    return (
        await session.execute(select(Ticket).where(Ticket.id == ticket_id, Ticket.tenant_id == tenant_id))
    ).scalar_one_or_none()


async def create_ticket(session: AsyncSession, tenant_id: uuid.UUID, payload: TicketCreate) -> Ticket:
    ticket = Ticket(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        customer_id=payload.customer_id,
        subject=payload.subject,
        status=payload.status,
        priority=payload.priority,
        source_connector_instance_id=payload.source_connector_instance_id,
        assigned_user_id=payload.assigned_user_id,
    )
    session.add(ticket)
    await session.flush()
    return ticket


async def update_ticket(session: AsyncSession, ticket: Ticket, payload: TicketUpdate) -> Ticket:
    if payload.subject is not None:
        ticket.subject = payload.subject
    if payload.status is not None:
        ticket.status = payload.status
    if payload.priority is not None:
        ticket.priority = payload.priority
    if payload.assigned_user_id is not None:
        ticket.assigned_user_id = payload.assigned_user_id
    await session.flush()
    return ticket


async def list_messages(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID, *, limit: int | None = None
) -> list[TicketMessage]:
    stmt = (
        select(TicketMessage)
        .where(TicketMessage.ticket_id == ticket_id, TicketMessage.tenant_id == tenant_id)
        .order_by(TicketMessage.created_at)
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def add_message(
    session: AsyncSession, tenant_id: uuid.UUID, ticket_id: uuid.UUID, payload: TicketMessageCreate
) -> TicketMessage:
    message = TicketMessage(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        ticket_id=ticket_id,
        author_type=payload.author_type,
        body=payload.body,
        attachments=payload.attachments,
    )
    session.add(message)
    await session.flush()
    return message


#: Which `ConnectorAdapter.perform_action` action/param-shape reaches a
#: customer directly, per connector type - and which `Customer` field
#: supplies the recipient id for that channel. Add a new channel here (not
#: a new function) once its adapter gains a customer-DM action the same
#: shape as these two - see `dispatch_reply_to_customer`.
_REPLY_DISPATCH_BY_CONNECTOR_TYPE: dict[str, tuple[str, str, str, str]] = {
    # connector_type_key -> (customer field, action, recipient param key, body param key)
    "instagram": ("external_ref", "send_direct_message", "recipient_id", "text"),
    "whatsapp": ("phone", "send_text_message", "to", "body"),
}


async def dispatch_reply_to_customer(
    session: AsyncSession, tenant_id: uuid.UUID, ticket: Ticket, body: str
) -> tuple[bool, str | None]:
    """Best-effort outbound send of a ticket reply to the customer over the
    channel the ticket originated from - `add_message` only ever writes the
    thread's own audit-trail row, it never dispatches anything (see that
    function and `router.py::add_ticket_message`, the "Send reply" button's
    literal request never actually reached the customer this stored until
    now). Returns `(dispatched, error)`: storing the message itself never
    depends on this succeeding, so a failure here is reported back, not
    raised - see `schemas.TicketMessageSendResult`.
    """
    if ticket.customer_id is None or ticket.source_connector_instance_id is None:
        return False, "This ticket has no linked customer/channel to reply to."

    customer = (
        await session.execute(select(Customer).where(Customer.id == ticket.customer_id, Customer.tenant_id == tenant_id))
    ).scalar_one_or_none()
    if customer is None:
        return False, "The linked customer record no longer exists."

    instance = await connector_service.get_instance(
        session, tenant_id=tenant_id, instance_id=ticket.source_connector_instance_id
    )
    if instance is None:
        return False, "The connector instance this ticket came from is no longer connected."

    connector_type_key = instance.connector_type.key
    dispatch_spec = _REPLY_DISPATCH_BY_CONNECTOR_TYPE.get(connector_type_key)
    if dispatch_spec is None:
        return False, f"Replying via {connector_type_key} isn't supported yet."

    customer_field, action, recipient_param, body_param = dispatch_spec
    recipient = getattr(customer, customer_field)
    if not recipient:
        return False, f"The linked customer has no {customer_field.replace('_', ' ')} on file."

    adapter = connector_registry.get_or_none(connector_type_key)
    if adapter is None:
        return False, f"No adapter registered for {connector_type_key}."

    params = {recipient_param: recipient, body_param: body}
    try:
        await adapter.perform_action(action=action, params=params, instance=instance, session=session)
    except Exception as exc:  # noqa: BLE001 - a provider-call failure is reported, not raised (see docstring)
        return False, str(exc)
    return True, None
