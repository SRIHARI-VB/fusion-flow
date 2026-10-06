"""`/api/v1/quick-replies` — channel-agnostic reusable text snippets.

Not mounted here — see `api.py`'s docstring; the integration wave mounts
`router` from this module under the `/api/v1` group.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.modules.connectors.deps import require_module_access
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.quick_replies import service as quick_replies_service
from fusionflow.modules.quick_replies.schemas import (
    QuickReplyCreate,
    QuickReplyOut,
    QuickReplyUpdate,
)

router = APIRouter(prefix="/quick-replies", tags=["quick-replies"], dependencies=[Depends(require_module_access("communication"))])


@router.get("", response_model=list[QuickReplyOut])
async def list_quick_replies(session: SessionDep, context: TenantContextDep) -> list[QuickReplyOut]:
    quick_replies = await quick_replies_service.list_quick_replies(session, tenant_id=context.tenant_id)
    return [QuickReplyOut.model_validate(quick_reply) for quick_reply in quick_replies]


@router.post("", response_model=QuickReplyOut, status_code=status.HTTP_201_CREATED)
async def create_quick_reply(
    payload: QuickReplyCreate, session: SessionDep, context: TenantContextDep
) -> QuickReplyOut:
    quick_reply = await quick_replies_service.create_quick_reply(
        session, tenant_id=context.tenant_id, payload=payload
    )
    await commit_and_keep_tenant_context(session)
    await session.refresh(quick_reply)
    return QuickReplyOut.model_validate(quick_reply)


@router.patch("/{quick_reply_id}", response_model=QuickReplyOut)
async def update_quick_reply(
    quick_reply_id: uuid.UUID,
    payload: QuickReplyUpdate,
    session: SessionDep,
    context: TenantContextDep,
) -> QuickReplyOut:
    quick_reply = await quick_replies_service.get_quick_reply(
        session, tenant_id=context.tenant_id, quick_reply_id=quick_reply_id
    )
    if quick_reply is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quick reply not found")
    quick_reply = await quick_replies_service.update_quick_reply(session, quick_reply, payload=payload)
    await commit_and_keep_tenant_context(session)
    await session.refresh(quick_reply)
    return QuickReplyOut.model_validate(quick_reply)


@router.delete("/{quick_reply_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_quick_reply(
    quick_reply_id: uuid.UUID, session: SessionDep, context: TenantContextDep
) -> None:
    quick_reply = await quick_replies_service.get_quick_reply(
        session, tenant_id=context.tenant_id, quick_reply_id=quick_reply_id
    )
    if quick_reply is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quick reply not found")
    await quick_replies_service.delete_quick_reply(session, quick_reply)
    await commit_and_keep_tenant_context(session)
