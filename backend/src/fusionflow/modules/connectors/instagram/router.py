"""`/api/v1/connectors/{instance_id}/instagram/*` — Instagram
connector-instance-level settings that aren't per-message workflow
actions.

Mounted separately from the generic `connectors` router (own prefix, own
tag), same convention as `connectors/whatsapp/router.py` for WhatsApp's
message-template CRUD - Ice Breakers are a one-time-per-account welcome
menu configuration, not a `PredefinedAutomation`/workflow at all, so they
don't belong in `predefined_automations`'s generic routes either.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import registry as connector_registry
from fusionflow.modules.connectors.instagram.schemas import (
    IceBreakerQuestion,
    IceBreakersRequest,
    InstagramMediaOut,
    InstagramMediaPage,
)

router = APIRouter(prefix="/connectors/{instance_id}/instagram", tags=["instagram"])

_NOT_FOUND = HTTPException(status_code=404, detail="Instagram connector instance not found")


async def _get_instance_or_404(session: SessionDep, tenant_id: uuid.UUID, instance_id: uuid.UUID):
    instance = await connector_service.get_instance(session, tenant_id=tenant_id, instance_id=instance_id)
    if instance is None or instance.connector_type.key != "instagram":
        raise _NOT_FOUND
    return instance


@router.get("/ice-breakers", response_model=list[IceBreakerQuestion])
async def get_ice_breakers(
    instance_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> list[IceBreakerQuestion]:
    instance = await _get_instance_or_404(session, context.tenant_id, instance_id)
    adapter = connector_registry.get("instagram")
    questions = await adapter.get_ice_breakers(instance=instance, session=session)
    return [IceBreakerQuestion(**q) for q in questions]


@router.put("/ice-breakers", response_model=list[IceBreakerQuestion])
async def set_ice_breakers(
    instance_id: uuid.UUID, payload: IceBreakersRequest, context: TenantContextDep, session: SessionDep
) -> list[IceBreakerQuestion]:
    instance = await _get_instance_or_404(session, context.tenant_id, instance_id)
    adapter = connector_registry.get("instagram")
    questions = [q.model_dump() for q in payload.questions]
    try:
        await adapter.set_ice_breakers(instance=instance, session=session, questions=questions)
    except (RuntimeError, ValueError) as exc:
        # A real, actionable failure (no credential on record, a rejected
        # Meta API call, etc.) - surfaced as a proper 400 with Meta's own
        # detail rather than an unhandled 500 with none at all.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return payload.questions


@router.get("/media", response_model=InstagramMediaPage)
async def list_media(
    instance_id: uuid.UUID,
    context: TenantContextDep,
    session: SessionDep,
    after: str | None = None,
    limit: int = 25,
) -> InstagramMediaPage:
    """One page of this account's own posts/reels - the post/reel picker
    for Comment Automation/Comment Moderation's "scope to specific
    posts/reels" option. `after`/`next_cursor` page through an account
    with hundreds of posts rather than fetching everything at once - pass
    a previous response's `next_cursor` back as `after` to continue."""
    instance = await _get_instance_or_404(session, context.tenant_id, instance_id)
    adapter = connector_registry.get("instagram")
    items, next_cursor = await adapter.list_media(instance=instance, session=session, after=after, limit=limit)
    return InstagramMediaPage(items=[InstagramMediaOut(**m) for m in items], next_cursor=next_cursor)
