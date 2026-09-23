from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.tickets.models import TicketMessageAuthorType, TicketStatus


class TicketCreate(BaseModel):
    customer_id: uuid.UUID | None = None
    subject: str = Field(min_length=1, max_length=300)
    status: TicketStatus = TicketStatus.OPEN
    priority: str = Field(default="medium", max_length=20)
    source_connector_instance_id: uuid.UUID | None = None
    assigned_user_id: uuid.UUID | None = None


class TicketUpdate(BaseModel):
    """Partial update — every field optional, unset fields are left alone."""

    subject: str | None = Field(default=None, min_length=1, max_length=300)
    status: TicketStatus | None = None
    priority: str | None = Field(default=None, max_length=20)
    assigned_user_id: uuid.UUID | None = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID | None
    # Denormalized for the list view; populated by the service layer's
    # join, not stored on the `tickets` row itself.
    customer_name: str | None = None
    subject: str
    status: TicketStatus
    priority: str
    source_connector_instance_id: uuid.UUID | None
    assigned_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class TicketMessageCreate(BaseModel):
    author_type: TicketMessageAuthorType
    body: str = Field(min_length=1)
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class TicketMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ticket_id: uuid.UUID
    author_type: TicketMessageAuthorType
    body: str
    attachments: list[dict[str, Any]]
    created_at: datetime


class TicketMessageSendResult(BaseModel):
    """Response for `POST /{ticket_id}/messages` - the message is always
    stored (it's the ticket thread's own audit trail, see
    `TicketMessage`'s docstring), but actually reaching the customer over
    their original channel is a separate, best-effort outbound call that
    can fail independently (no linked customer/connector instance, the
    channel's own send API rejecting it, ...). Surfacing both lets the
    frontend show "saved but not delivered" instead of a misleading
    "Send reply" success with no actual delivery - the bug this type
    exists to stop being silent about."""

    message: TicketMessageOut
    dispatched: bool
    dispatch_error: str | None = None
