"""`/api/v1/predefined-automations` - guided/wizard-configured automations.

Every route here is generic across automation types (create/list/get/
update/pause-resume/delete) - a route never branches on `automation_type`
beyond looking it up in the registry (`registry.py`), matching the
connector framework's identical "generic routes, provider-specific logic
lives in the registered plugin" shape.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.predefined_automations import service as automations_service
from fusionflow.modules.predefined_automations.registry import registry
from fusionflow.modules.predefined_automations.schemas import (
    PredefinedAutomationCreate,
    PredefinedAutomationOut,
    PredefinedAutomationSetActive,
    PredefinedAutomationTypeOut,
    PredefinedAutomationUpdate,
)
from fusionflow.modules.predefined_automations.service import PredefinedAutomationError

router = APIRouter(prefix="/predefined-automations", tags=["predefined-automations"])

_NOT_FOUND = HTTPException(status_code=404, detail="Predefined automation not found")


def _http(exc: PredefinedAutomationError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/types", response_model=list[PredefinedAutomationTypeOut])
async def list_automation_types(
    connector_type_key: str | None = None,
) -> list[PredefinedAutomationTypeOut]:
    """The registry catalog - what a channel's "Automations" list page
    offers as "+ New Automation" options. `connector_type_key`, when
    given, scopes to just that channel's types."""
    types = (
        registry.for_connector_type(connector_type_key)
        if connector_type_key is not None
        else registry.all_types()
    )
    return [
        PredefinedAutomationTypeOut(
            automation_type=t.automation_type,
            connector_type_key=t.connector_type_key,
            label=t.label,
            description=t.description,
        )
        for t in types
    ]


@router.get("", response_model=list[PredefinedAutomationOut])
async def list_automations(
    context: TenantContextDep, session: SessionDep, connector_type_key: str | None = None
) -> list[PredefinedAutomationOut]:
    automations = await automations_service.list_predefined_automations(
        session, tenant_id=context.tenant_id, connector_type_key=connector_type_key
    )
    return [PredefinedAutomationOut.model_validate(a) for a in automations]


@router.post("", response_model=PredefinedAutomationOut, status_code=201)
async def create_automation(
    payload: PredefinedAutomationCreate, context: TenantContextDep, session: SessionDep
) -> PredefinedAutomationOut:
    try:
        automation = await automations_service.create_predefined_automation(
            session,
            tenant_id=context.tenant_id,
            connector_instance_id=payload.connector_instance_id,
            automation_type=payload.automation_type,
            config=payload.config,
            name=payload.name,
            created_by=context.user.id,
        )
    except PredefinedAutomationError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    return PredefinedAutomationOut.model_validate(automation)


@router.get("/{automation_id}", response_model=PredefinedAutomationOut)
async def get_automation(
    automation_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> PredefinedAutomationOut:
    automation = await automations_service.get_predefined_automation(
        session, tenant_id=context.tenant_id, automation_id=automation_id
    )
    if automation is None:
        raise _NOT_FOUND
    return PredefinedAutomationOut.model_validate(automation)


@router.patch("/{automation_id}", response_model=PredefinedAutomationOut)
async def update_automation(
    automation_id: uuid.UUID,
    payload: PredefinedAutomationUpdate,
    context: TenantContextDep,
    session: SessionDep,
) -> PredefinedAutomationOut:
    automation = await automations_service.get_predefined_automation(
        session, tenant_id=context.tenant_id, automation_id=automation_id
    )
    if automation is None:
        raise _NOT_FOUND
    try:
        automation = await automations_service.update_predefined_automation(
            session, automation, config=payload.config, updated_by=context.user.id
        )
    except PredefinedAutomationError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    # `updated_at` is DB-computed (`onupdate=func.now()`, TimestampMixin) -
    # unlike an INSERT's server_default, SQLAlchemy does not eagerly fetch
    # an UPDATE's onupdate value via RETURNING, so it's left expired after
    # flush/commit. Left alone, `model_validate` below triggers a lazy
    # load for it outside any async/greenlet context the instant Pydantic
    # touches it - `MissingGreenlet` - a real 500 seen in production. Same
    # fix as `connectors/service.py::connect()`'s identical bug.
    await session.refresh(automation, attribute_names=["updated_at"])
    return PredefinedAutomationOut.model_validate(automation)


@router.post("/{automation_id}/active", response_model=PredefinedAutomationOut)
async def set_automation_active(
    automation_id: uuid.UUID,
    payload: PredefinedAutomationSetActive,
    context: TenantContextDep,
    session: SessionDep,
) -> PredefinedAutomationOut:
    automation = await automations_service.get_predefined_automation(
        session, tenant_id=context.tenant_id, automation_id=automation_id
    )
    if automation is None:
        raise _NOT_FOUND
    try:
        automation = await automations_service.set_active(
            session, automation, is_active=payload.is_active, actor_id=context.user.id
        )
    except PredefinedAutomationError as exc:
        raise _http(exc) from exc
    await commit_and_keep_tenant_context(session)
    # Same `updated_at` refresh as `update_automation` above - `set_active`
    # also flushes an UPDATE that touches the onupdate column.
    await session.refresh(automation, attribute_names=["updated_at"])
    return PredefinedAutomationOut.model_validate(automation)


@router.delete("/{automation_id}", status_code=204)
async def delete_automation(
    automation_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> None:
    automation = await automations_service.get_predefined_automation(
        session, tenant_id=context.tenant_id, automation_id=automation_id
    )
    if automation is None:
        raise _NOT_FOUND
    await automations_service.delete_predefined_automation(session, automation)
    await commit_and_keep_tenant_context(session)
