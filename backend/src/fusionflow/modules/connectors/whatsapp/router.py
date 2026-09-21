"""`/api/v1/connectors/{instance_id}/whatsapp/*` — WhatsApp message
template catalog CRUD + Meta sync.

Mounted separately from the generic `connectors` router (own prefix,
own tag) since this is WhatsApp-specific, not part of the generic
connector lifecycle surface - see `whatsapp/service.py`'s module
docstring for the domain-logic split this router maps onto.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.connectors.whatsapp import service as whatsapp_service
from fusionflow.modules.connectors.whatsapp.schemas import (
    WhatsAppTemplateCreateRequest,
    WhatsAppTemplateOut,
    WhatsAppTemplateUpdateRequest,
)
from fusionflow.modules.connectors.whatsapp.service import ConnectorError

router = APIRouter(prefix="/connectors/{instance_id}/whatsapp", tags=["whatsapp"])


def _http(exc: ConnectorError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/templates", response_model=list[WhatsAppTemplateOut])
async def list_whatsapp_templates(
    instance_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> list[WhatsAppTemplateOut]:
    templates = await whatsapp_service.list_templates(
        session, tenant_id=context.tenant_id, connector_instance_id=instance_id
    )
    return [WhatsAppTemplateOut.model_validate(t) for t in templates]


@router.post("/templates", response_model=WhatsAppTemplateOut, status_code=status.HTTP_201_CREATED)
async def create_whatsapp_template(
    instance_id: uuid.UUID,
    payload: WhatsAppTemplateCreateRequest,
    context: TenantContextDep,
    session: SessionDep,
) -> WhatsAppTemplateOut:
    try:
        template = await whatsapp_service.create_template(
            session,
            tenant_id=context.tenant_id,
            connector_instance_id=instance_id,
            name=payload.name,
            language=payload.language,
            category=payload.category,
            status=payload.status,
            components=payload.components,
        )
    except ConnectorError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    return WhatsAppTemplateOut.model_validate(template)


@router.patch("/templates/{template_id}", response_model=WhatsAppTemplateOut)
async def update_whatsapp_template(
    instance_id: uuid.UUID,
    template_id: uuid.UUID,
    payload: WhatsAppTemplateUpdateRequest,
    context: TenantContextDep,
    session: SessionDep,
) -> WhatsAppTemplateOut:
    try:
        template = await whatsapp_service.update_template(
            session,
            tenant_id=context.tenant_id,
            template_id=template_id,
            category=payload.category,
            status=payload.status,
            components=payload.components,
        )
    except ConnectorError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    # `updated_at` is DB-computed (`onupdate=func.now()`) and left expired
    # after an UPDATE flush - see `predefined_automations/router.py`'s
    # identical fix for the full explanation of the MissingGreenlet crash
    # this avoids.
    await session.refresh(template, attribute_names=["updated_at"])
    return WhatsAppTemplateOut.model_validate(template)


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_whatsapp_template(
    instance_id: uuid.UUID, template_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> None:
    try:
        await whatsapp_service.delete_template(session, tenant_id=context.tenant_id, template_id=template_id)
    except ConnectorError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)


@router.post("/templates/sync", response_model=list[WhatsAppTemplateOut])
async def sync_whatsapp_templates(
    instance_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> list[WhatsAppTemplateOut]:
    try:
        templates = await whatsapp_service.sync_from_meta(
            session, tenant_id=context.tenant_id, connector_instance_id=instance_id
        )
    except ConnectorError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    # Same `updated_at` refresh as `update_whatsapp_template` above - sync
    # upserts (creates or updates) each template row.
    for t in templates:
        await session.refresh(t, attribute_names=["updated_at"])
    return [WhatsAppTemplateOut.model_validate(t) for t in templates]
