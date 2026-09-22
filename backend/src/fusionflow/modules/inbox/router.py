"""`/inbox` — Unified Inbox routes.

Not mounted here — same convention as `modules/customers/router.py`'s
docstring: the coordinating integration wave mounts `router` into
`fusionflow.api.api_router`, giving final paths under
`/api/v1/inbox/...`.

Every handler below calls straight into `service.py`; `InboxError` is
mapped to an HTTP response via `_http`, mirroring
`connectors/router.py::_http`'s identical pattern.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.inbox import service as inbox_service
from fusionflow.modules.inbox.schemas import (
    AssignAgentRequest,
    ConversationOut,
    MessageOut,
    SendMessageRequest,
    SetAutomationPausedRequest,
)
from fusionflow.modules.inbox.service import InboxError

router = APIRouter(prefix="/inbox", tags=["inbox"])


def _http(exc: InboxError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(context: TenantContextDep, session: SessionDep) -> list[ConversationOut]:
    conversations = await inbox_service.list_conversations(session, tenant_id=context.tenant_id)
    return [inbox_service.to_conversation_out(c) for c in conversations]


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> list[MessageOut]:
    try:
        messages = await inbox_service.list_messages(
            session, tenant_id=context.tenant_id, conversation_id=conversation_id
        )
    except InboxError as exc:
        raise _http(exc) from exc
    return [MessageOut.model_validate(m) for m in messages]


@router.post("/conversations/{conversation_id}/messages", response_model=MessageOut)
async def send_message(
    conversation_id: uuid.UUID,
    payload: SendMessageRequest,
    context: TenantContextDep,
    session: SessionDep,
) -> MessageOut:
    try:
        message = await inbox_service.send_message(
            session, tenant_id=context.tenant_id, conversation_id=conversation_id, content=payload.content
        )
    except InboxError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    return MessageOut.model_validate(message)


@router.post("/conversations/{conversation_id}/read", response_model=ConversationOut)
async def mark_conversation_read(
    conversation_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> ConversationOut:
    try:
        conversation = await inbox_service.mark_read(
            session, tenant_id=context.tenant_id, conversation_id=conversation_id
        )
    except InboxError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    # `updated_at` is DB-computed (`onupdate=func.now()`) and left expired
    # after an UPDATE flush - see `predefined_automations/router.py`'s
    # identical fix for the full explanation of the MissingGreenlet crash
    # this avoids.
    await session.refresh(conversation, attribute_names=["updated_at"])
    return inbox_service.to_conversation_out(conversation)


@router.post("/conversations/{conversation_id}/assign", response_model=ConversationOut)
async def assign_conversation_agent(
    conversation_id: uuid.UUID,
    payload: AssignAgentRequest,
    context: TenantContextDep,
    session: SessionDep,
) -> ConversationOut:
    try:
        conversation = await inbox_service.assign_agent(
            session,
            tenant_id=context.tenant_id,
            conversation_id=conversation_id,
            agent_id=payload.agent_id,
        )
    except InboxError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    # Same `updated_at` refresh as `mark_conversation_read` above.
    await session.refresh(conversation, attribute_names=["updated_at"])
    return inbox_service.to_conversation_out(conversation)


@router.post("/conversations/{conversation_id}/automation-paused", response_model=ConversationOut)
async def set_conversation_automation_paused(
    conversation_id: uuid.UUID,
    payload: SetAutomationPausedRequest,
    context: TenantContextDep,
    session: SessionDep,
) -> ConversationOut:
    """Agent-facing pause/resume toggle - the "human handoff" predefined
    automation's `inbox.pause_automation` node sets this mid-run; this
    endpoint is how an agent clears it again (or pauses one manually,
    without waiting for that automation to fire)."""
    try:
        conversation = await inbox_service.set_automation_paused(
            session, tenant_id=context.tenant_id, conversation_id=conversation_id, paused=payload.paused
        )
    except InboxError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    # Same `updated_at` refresh as `mark_conversation_read` above.
    await session.refresh(conversation, attribute_names=["updated_at"])
    return inbox_service.to_conversation_out(conversation)
