"""Unified Inbox models: a cross-channel conversation/message store so a
human agent can read and reply to customer messages from WhatsApp,
Instagram, Telegram, and Facebook in one place.

Provider-agnostic by design, mirroring `modules.connectors.base`'s
framework guarantee: `Conversation`/`Message` never branch on connector
type themselves - `service.py` resolves the right adapter via
`base.registry.get(instance.connector_type.key)` when sending, and each
provider adapter's `handle_webhook` calls `service.upsert_inbound_message`
for an inbound message, uniformly, regardless of provider.

`Conversation` is one row per (tenant, connector_instance, external
contact) - `external_contact_id` is deliberately an opaque, provider-shape
string (a WhatsApp/Telegram-ish phone number or chat id, an
Instagram-scoped id, or a Messenger PSID); nothing here ever parses or
validates its shape.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin
from fusionflow.modules.connectors.models import ConnectorInstance


class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageSenderType(str, enum.Enum):
    CUSTOMER = "customer"
    AGENT = "agent"


class Conversation(Base, TenantScopedMixin, TimestampMixin):
    """One thread with one customer contact on one connector instance."""

    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "connector_instance_id",
            "external_contact_id",
            name="uq_conversation_tenant_instance_contact",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_instance_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # The provider's own id for this contact - a phone number (WhatsApp/
    # Telegram-ish), an Instagram-scoped id, or a Messenger PSID. Opaque
    # string, provider-specific shape - never parsed here.
    external_contact_id: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    assigned_agent_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unread_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Set by the `inbox.pause_automation` node (the "human handoff"
    # predefined-automation action) - while true, the outbox poller's
    # dispatch gate (`inbox_service.is_automation_paused`, checked from
    # `engine/outbox_poller.py`) skips starting a new run for any
    # conversational trigger on this conversation, so a human agent (or
    # the customer, next time they message) isn't fighting an automation
    # that keeps replying. Cleared by an agent resuming it from the Inbox
    # UI, or automatically once `automation_paused_until` passes (an
    # optional SLA timer - see that column) - whichever comes first.
    automation_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    # Optional SLA auto-resume deadline - set alongside `automation_paused`
    # only when the triggering handoff automation configured an
    # `auto_resume_after_hours`. `None` means "stays paused until an agent
    # manually resumes it" (the original, still-supported behavior).
    # `inbox_service.is_automation_paused` lazily clears `automation_paused`
    # the first time it notices this has passed, rather than needing its
    # own sweep.
    automation_paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # A reset changes conversational state, never the customer's identity.
    # The timestamp also rejects late deliveries from before the reset.
    flow_reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    flow_reset_pending: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Read-only convenience relationship for eager-loading in
    # `service.list_conversations` (no `back_populates` needed on
    # `ConnectorInstance` - this direction is all `to_conversation_out`
    # needs).
    connector_instance: Mapped[ConnectorInstance] = relationship(viewonly=True)


class Message(Base, TenantScopedMixin):
    """One message (inbound from the customer, or outbound from an agent)
    within a `Conversation`."""

    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[MessageDirection] = mapped_column(
        Enum(MessageDirection, name="message_direction", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    sender_type: Mapped[MessageSenderType] = mapped_column(
        Enum(MessageSenderType, name="message_sender_type", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    external_message_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
