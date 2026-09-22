"""`/api/v1/broadcast-campaigns` - scheduled bulk WhatsApp sends."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.broadcast_campaigns import service as campaigns_service
from fusionflow.modules.broadcast_campaigns.models import BroadcastCampaign
from fusionflow.modules.broadcast_campaigns.schemas import (
    BroadcastCampaignCreate,
    BroadcastCampaignOut,
    BroadcastCampaignSetActive,
)
from fusionflow.modules.broadcast_campaigns.service import BroadcastCampaignError

router = APIRouter(prefix="/broadcast-campaigns", tags=["broadcast-campaigns"])

_NOT_FOUND = HTTPException(status_code=404, detail="Broadcast campaign not found")


def _http(exc: BroadcastCampaignError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


async def _to_out(session: SessionDep, campaign: BroadcastCampaign) -> BroadcastCampaignOut:
    schedule = await campaigns_service.get_schedule_for_campaign(session, campaign)
    return BroadcastCampaignOut(
        id=campaign.id,
        connector_instance_id=campaign.connector_instance_id,
        name=campaign.name,
        message_text=campaign.message_text,
        recipient_phone_numbers=campaign.recipient_phone_numbers,
        media_url=campaign.media_url,
        media_type=campaign.media_type,
        location_latitude=campaign.location_latitude,
        location_longitude=campaign.location_longitude,
        location_name=campaign.location_name,
        location_address=campaign.location_address,
        workflow_id=campaign.workflow_id,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
        next_run_at=schedule.next_run_at if schedule else None,
        is_active=schedule.is_active if schedule else False,
        last_run_at=schedule.last_run_at if schedule else None,
        last_run_status=schedule.last_run_status if schedule else None,
    )


@router.get("", response_model=list[BroadcastCampaignOut])
async def list_campaigns(context: TenantContextDep, session: SessionDep) -> list[BroadcastCampaignOut]:
    campaigns = await campaigns_service.list_campaigns(session, tenant_id=context.tenant_id)
    return [await _to_out(session, c) for c in campaigns]


@router.post("", response_model=BroadcastCampaignOut, status_code=201)
async def create_campaign(
    payload: BroadcastCampaignCreate, context: TenantContextDep, session: SessionDep
) -> BroadcastCampaignOut:
    try:
        campaign = await campaigns_service.create_campaign(
            session,
            tenant_id=context.tenant_id,
            connector_instance_id=payload.connector_instance_id,
            name=payload.name,
            message_text=payload.message_text,
            recipient_phone_numbers=payload.recipient_phone_numbers,
            scheduled_at=payload.scheduled_at,
            created_by=context.user.id,
            media_url=payload.media_url,
            media_type=payload.media_type,
            location_latitude=payload.location_latitude,
            location_longitude=payload.location_longitude,
            location_name=payload.location_name,
            location_address=payload.location_address,
        )
    except BroadcastCampaignError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    return await _to_out(session, campaign)


@router.get("/{campaign_id}", response_model=BroadcastCampaignOut)
async def get_campaign(campaign_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> BroadcastCampaignOut:
    campaign = await campaigns_service.get_campaign(session, tenant_id=context.tenant_id, campaign_id=campaign_id)
    if campaign is None:
        raise _NOT_FOUND
    return await _to_out(session, campaign)


@router.post("/{campaign_id}/active", response_model=BroadcastCampaignOut)
async def set_campaign_active(
    campaign_id: uuid.UUID, payload: BroadcastCampaignSetActive, context: TenantContextDep, session: SessionDep
) -> BroadcastCampaignOut:
    campaign = await campaigns_service.get_campaign(session, tenant_id=context.tenant_id, campaign_id=campaign_id)
    if campaign is None:
        raise _NOT_FOUND
    try:
        campaign = await campaigns_service.set_active(session, campaign, is_active=payload.is_active)
    except BroadcastCampaignError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    # `updated_at` is DB-computed (`onupdate=func.now()`) - an UPDATE flush
    # leaves it expired (unlike an INSERT's server_default, which SQLAlchemy
    # fetches eagerly via RETURNING), so a synchronous access below would
    # otherwise trigger a lazy load outside any async/greenlet context
    # (`MissingGreenlet`) - see `predefined_automations/router.py`'s
    # identical fix for the full explanation.
    await session.refresh(campaign, attribute_names=["updated_at"])
    return await _to_out(session, campaign)


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> None:
    campaign = await campaigns_service.get_campaign(session, tenant_id=context.tenant_id, campaign_id=campaign_id)
    if campaign is None:
        raise _NOT_FOUND
    await campaigns_service.delete_campaign(session, campaign)
    await commit_and_keep_tenant_context(session)
