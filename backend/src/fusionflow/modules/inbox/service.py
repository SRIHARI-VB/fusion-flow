"""Unified Inbox service.

Provider-agnostic, matching `modules.connectors.service`'s framework
guarantee: the only provider-aware code in this module is `send_message`'s
dispatch table, which resolves the right adapter via
`base.registry.get(instance.connector_type.key)` and calls its
`perform_action` - nothing here branches on provider for anything else.

Deliberately framework-free (raises `InboxError`, not `HTTPException`),
matching `modules/connectors/service.py`'s `ConnectorError` convention -
`router.py` maps `InboxError` to an HTTP response.

Commit convention: every function here matches the rest of this codebase's
"services never commit, the router owns the transaction boundary" rule -
`await session.flush()` only - with ONE exception: `upsert_inbound_message`
is called from adapter `handle_webhook` code, which itself never commits
either (the caller, `webhooks.py::_dispatch`, commits once after
`handle_webhook` returns) - so `upsert_inbound_message` also only flushes,
never commits.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import registry as connector_registry
from fusionflow.modules.connectors.models import ConnectorInstance
from fusionflow.modules.inbox.models import Conversation, Message, MessageDirection, MessageSenderType
from fusionflow.modules.inbox.schemas import ConversationOut


class InboxError(Exception):
    """Domain-level inbox failure. `status_code` is the HTTP status to emit."""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def to_conversation_out(conversation: Conversation) -> ConversationOut:
    """Conversation -> DTO. Requires `conversation.connector_instance.
    connector_type` to already be loaded (see `_conversation_query`'s
    `selectinload` chain) - never lazy-loads here, so this stays usable
    from a webhook-ingestion path that may not have full ORM relationship
    access set up. Mirrors `connectors/service.py::to_instance_out`."""
    return ConversationOut(
        id=conversation.id,
        connector_instance_id=conversation.connector_instance_id,
        connector_type_key=conversation.connector_instance.connector_type.key,
        external_contact_id=conversation.external_contact_id,
        display_name=conversation.display_name,
        assigned_agent_id=conversation.assigned_agent_id,
        last_message_at=conversation.last_message_at,
        unread_count=conversation.unread_count,
        automation_paused=conversation.automation_paused,
        automation_paused_until=conversation.automation_paused_until,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _conversation_query():
    return select(Conversation).options(
        selectinload(Conversation.connector_instance).selectinload(ConnectorInstance.connector_type)
    )


async def list_conversations(session: AsyncSession, *, tenant_id: uuid.UUID) -> Sequence[Conversation]:
    rows = await session.execute(
        _conversation_query()
        .where(Conversation.tenant_id == tenant_id)
        .order_by(Conversation.last_message_at.desc())
    )
    return list(rows.scalars().all())


async def get_conversation(
    session: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation | None:
    return (
        await session.execute(
            _conversation_query().where(
                Conversation.id == conversation_id, Conversation.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()


async def _get_conversation_or_404(
    session: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    conversation = await get_conversation(session, tenant_id=tenant_id, conversation_id=conversation_id)
    if conversation is None:
        raise InboxError("Conversation not found", status_code=404)
    return conversation


async def list_messages(
    session: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, limit: int = 200
) -> Sequence[Message]:
    # Verifies the conversation belongs to this tenant first, so the
    # router doesn't need a separate existence check before calling this.
    await _get_conversation_or_404(session, tenant_id=tenant_id, conversation_id=conversation_id)
    rows = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id, Message.tenant_id == tenant_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return list(rows.scalars().all())


async def upsert_inbound_message(
    session: AsyncSession,
    *,
    instance: ConnectorInstance,
    external_contact_id: str,
    content: str,
    external_message_id: str | None,
    display_name: str | None = None,
    resolve_display_name: Callable[[], Awaitable[str | None]] | None = None,
) -> Message:
    """Find-or-create the `Conversation` for this (instance, contact), bump
    its unread/last-message bookkeeping, then create+add the inbound
    `Message`. Called from adapter `handle_webhook` code - never commits,
    only flushes (see module docstring).

    `resolve_display_name`, when given, is only ever awaited if a display
    name is still genuinely unknown (a brand-new conversation, or an
    existing one whose `display_name` never resolved yet) - a channel
    whose webhook payload doesn't carry the sender's name inline (e.g.
    Instagram DMs - see `instagram/adapter.py::get_user_profile`) needs an
    extra Graph API call to resolve it, and this keeps that call from
    firing on every single inbound message once it's already known.
    """
    now = datetime.now(timezone.utc)
    conversation = (
        await session.execute(
            select(Conversation).where(
                Conversation.tenant_id == instance.tenant_id,
                Conversation.connector_instance_id == instance.id,
                Conversation.external_contact_id == external_contact_id,
            )
        )
    ).scalar_one_or_none()

    if display_name is None and resolve_display_name is not None:
        if conversation is None or conversation.display_name is None:
            display_name = await resolve_display_name()

    if conversation is None:
        conversation = Conversation(
            id=uuid.uuid4(),
            tenant_id=instance.tenant_id,
            connector_instance_id=instance.id,
            external_contact_id=external_contact_id,
            display_name=display_name,
            last_message_at=now,
            unread_count=1,
        )
        session.add(conversation)
    else:
        conversation.last_message_at = now
        conversation.unread_count += 1
        if conversation.display_name is None and display_name:
            conversation.display_name = display_name

    await session.flush()

    message = Message(
        id=uuid.uuid4(),
        tenant_id=instance.tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.INBOUND,
        sender_type=MessageSenderType.CUSTOMER,
        content=content,
        external_message_id=external_message_id,
    )
    session.add(message)
    await session.flush()
    return message


async def send_message(
    session: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, content: str
) -> Message:
    """An agent's reply: dispatch it out through the right provider
    adapter (via the generic `perform_action` escape hatch, same as the
    workflow engine's `connector.action` node type), then record it as an
    outbound `Message`. Never commits - the router owns the transaction
    boundary."""
    conversation = await _get_conversation_or_404(session, tenant_id=tenant_id, conversation_id=conversation_id)

    instance = await connector_service.get_instance(
        session, tenant_id=tenant_id, instance_id=conversation.connector_instance_id
    )
    if instance is None:
        raise InboxError("Connector instance not found", status_code=404)

    type_key = instance.connector_type.key
    adapter = connector_registry.get(type_key)
    if type_key == "whatsapp":
        await adapter.perform_action(
            action="send_text_message",
            params={"to": conversation.external_contact_id, "body": content},
            instance=instance,
            session=session,
        )
    elif type_key == "instagram":
        await adapter.perform_action(
            action="send_direct_message",
            params={"recipient_id": conversation.external_contact_id, "text": content},
            instance=instance,
            session=session,
        )
    elif type_key == "telegram":
        await adapter.perform_action(
            action="send_message",
            params={"chat_id": conversation.external_contact_id, "text": content},
            instance=instance,
            session=session,
        )
    elif type_key == "facebook":
        await adapter.perform_action(
            action="send_message",
            params={"recipient_id": conversation.external_contact_id, "text": content},
            instance=instance,
            session=session,
        )
    else:
        raise InboxError(f"Sending is not supported for connector type {type_key!r}", status_code=400)

    message = Message(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        conversation_id=conversation.id,
        direction=MessageDirection.OUTBOUND,
        sender_type=MessageSenderType.AGENT,
        content=content,
        external_message_id=None,
    )
    session.add(message)
    conversation.last_message_at = datetime.now(timezone.utc)
    await session.flush()
    return message


async def mark_read(session: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> Conversation:
    conversation = await _get_conversation_or_404(session, tenant_id=tenant_id, conversation_id=conversation_id)
    conversation.unread_count = 0
    await session.flush()
    return conversation


async def assign_agent(
    session: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, agent_id: uuid.UUID | None
) -> Conversation:
    conversation = await _get_conversation_or_404(session, tenant_id=tenant_id, conversation_id=conversation_id)
    conversation.assigned_agent_id = agent_id
    await session.flush()
    return conversation


async def set_automation_paused(
    session: AsyncSession, *, tenant_id: uuid.UUID, conversation_id: uuid.UUID, paused: bool
) -> Conversation:
    """Agent-facing pause/resume (Inbox UI's toggle) - resolves by
    `conversation_id`. See `pause_automation_for_contact` for the
    automation-side counterpart (resolves by contact, since that's what a
    running workflow has on hand)."""
    conversation = await _get_conversation_or_404(session, tenant_id=tenant_id, conversation_id=conversation_id)
    conversation.automation_paused = paused
    conversation.automation_paused_until = None
    await session.flush()
    return conversation


async def pause_automation_for_contact(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connector_instance_id: uuid.UUID,
    external_contact_id: str,
    resume_after_hours: float | None = None,
) -> None:
    """The `inbox.pause_automation` workflow node's implementation - called
    mid-run, so by definition the inbound message that triggered this run
    already went through `upsert_inbound_message` and the `Conversation`
    row already exists; a missing row here would mean this node ran for a
    trigger type with no corresponding Inbox conversation (e.g. a comment,
    not a DM), which is a wizard/config mistake, not a runtime race - a
    no-op is the safe response, not an error that fails the whole run.

    `resume_after_hours`, when given (the Human Handoff automation's
    optional SLA timer field), sets `automation_paused_until` - see
    `is_automation_paused`'s lazy-expiry check below for how that actually
    resumes it. `None` (the default) means "stays paused until an agent
    manually resumes it", the original behavior.
    """
    conversation = (
        await session.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.connector_instance_id == connector_instance_id,
                Conversation.external_contact_id == external_contact_id,
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        return
    conversation.automation_paused = True
    conversation.automation_paused_until = (
        datetime.now(timezone.utc) + timedelta(hours=resume_after_hours) if resume_after_hours else None
    )
    await session.flush()


async def is_automation_paused(
    session: AsyncSession, *, tenant_id: uuid.UUID, connector_instance_id: uuid.UUID, external_contact_id: str
) -> bool:
    """The outbox poller's dispatch gate (`engine/outbox_poller.py`) -
    checked before starting a new run for a conversational trigger type.
    `False` (never paused) when no `Conversation` row exists yet, same
    "missing means default state" convention as every other lookup here.

    Lazily clears an expired SLA-timer pause right here (rather than
    needing a separate sweep, unlike `flow.delay`'s resume - a resume
    here has nothing to actually DO beyond flipping the flag back, so
    there's no reason to wait for the next poll cycle when this check
    already runs on every dispatch attempt) - the next conversational
    trigger for this contact after the timer passes finds it unpaused."""
    conversation = (
        await session.execute(
            select(Conversation).where(
                Conversation.tenant_id == tenant_id,
                Conversation.connector_instance_id == connector_instance_id,
                Conversation.external_contact_id == external_contact_id,
            )
        )
    ).scalar_one_or_none()
    if conversation is None or not conversation.automation_paused:
        return False
    if conversation.automation_paused_until is not None and conversation.automation_paused_until <= datetime.now(
        timezone.utc
    ):
        conversation.automation_paused = False
        conversation.automation_paused_until = None
        await session.flush()
        return False
    return True
