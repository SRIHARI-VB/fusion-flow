"""`/api/v1/custom-fields` — field_definitions CRUD + global template listing/apply.

Not mounted here: per the wave's coordination rules, `api.py`
(`/api/v1` router group) is owned by another agent's pass. Mount as:

    from fusionflow.modules.custom_fields.router import router as custom_fields_router
    api_router.include_router(custom_fields_router)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from fusionflow.core.deps import CurrentUserDep, SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.connectors.deps import require_module_access
from fusionflow.modules.custom_fields import service as custom_fields_service
from fusionflow.modules.custom_fields.models import EntityType
from fusionflow.modules.custom_fields.schemas import (
    ApplyTemplateResponse,
    FieldDefinitionCreate,
    FieldDefinitionOut,
    FieldDefinitionUpdate,
    FieldTemplateOut,
)

router = APIRouter(prefix="/custom-fields", tags=["custom-fields"])

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field definition not found")

# Per-route, not router-level: GET /templates deliberately has no tenant
# context (CurrentUserDep only - the onboarding wizard reads it before a
# business is fully set up) and must stay reachable, which a router-level
# `dependencies=[]` cannot selectively exclude one route from.
_require_custom_fields = Depends(require_module_access("custom_fields"))


@router.get("/definitions", response_model=list[FieldDefinitionOut])
async def list_definitions(
    context: TenantContextDep,
    session: SessionDep,
    entity_type: EntityType | None = Query(default=None),
    _gate=_require_custom_fields,
) -> list[FieldDefinitionOut]:
    definitions = await custom_fields_service.list_field_definitions(
        session, tenant_id=context.tenant_id, entity_type=entity_type
    )
    return [FieldDefinitionOut.model_validate(d) for d in definitions]


@router.post("/definitions", response_model=FieldDefinitionOut, status_code=status.HTTP_201_CREATED)
async def create_definition(
    payload: FieldDefinitionCreate,
    context: TenantContextDep,
    session: SessionDep,
    _gate=_require_custom_fields,
) -> FieldDefinitionOut:
    # Enforced inline (not via the generic `enforce_resource_limit`
    # dependency the other 7 limitable resources use) because the limit
    # applies per `payload.entity_type`, not per tenant overall - see
    # `custom_fields_service.count_field_definitions`'s docstring. A
    # dependency resolved before the body is parsed has no clean way to
    # know which entity_type this particular create is for.
    limit = await admin_service.get_resource_limit(
        session, tenant_id=context.tenant_id, resource_key="custom_fields"
    )
    if limit is not None:
        current = await custom_fields_service.count_field_definitions(
            session, context.tenant_id, entity_type=payload.entity_type
        )
        if current >= limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You've reached your plan's limit of {limit} custom fields for {payload.entity_type.value}.",
            )

    definition = await custom_fields_service.create_field_definition(
        session, tenant_id=context.tenant_id, payload=payload
    )
    await commit_and_keep_tenant_context(session)
    return FieldDefinitionOut.model_validate(definition)


@router.patch("/definitions/{definition_id}", response_model=FieldDefinitionOut)
async def update_definition(
    definition_id: uuid.UUID,
    payload: FieldDefinitionUpdate,
    context: TenantContextDep,
    session: SessionDep,
    _gate=_require_custom_fields,
) -> FieldDefinitionOut:
    definition = await custom_fields_service.get_field_definition(
        session, tenant_id=context.tenant_id, definition_id=definition_id
    )
    if definition is None:
        raise _NOT_FOUND
    definition = await custom_fields_service.update_field_definition(session, definition, payload)
    await commit_and_keep_tenant_context(session)
    return FieldDefinitionOut.model_validate(definition)


@router.delete("/definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_definition(
    definition_id: uuid.UUID, context: TenantContextDep, session: SessionDep, _gate=_require_custom_fields
) -> None:
    definition = await custom_fields_service.get_field_definition(
        session, tenant_id=context.tenant_id, definition_id=definition_id
    )
    if definition is None:
        raise _NOT_FOUND
    await custom_fields_service.delete_field_definition(session, definition)
    await commit_and_keep_tenant_context(session)


@router.get("/templates", response_model=list[FieldTemplateOut])
async def list_templates(
    user: CurrentUserDep,
    session: SessionDep,
    vertical: str | None = Query(default=None),
    entity_type: EntityType | None = Query(default=None),
) -> list[FieldTemplateOut]:
    """Global (platform-seeded) templates - not tenant-scoped.

    Depends only on `get_current_user`, not tenant context: the onboarding
    wizard's "apply a template" step reads this to populate its picker, and
    a template is the same platform-wide resource for every tenant, so no
    `SET LOCAL` / RLS scoping applies here.
    """
    templates = await custom_fields_service.list_templates(session, vertical=vertical, entity_type=entity_type)
    return [FieldTemplateOut.model_validate(t) for t in templates]


@router.post("/templates/{template_id}/apply", response_model=ApplyTemplateResponse)
async def apply_template(
    template_id: uuid.UUID, context: TenantContextDep, session: SessionDep, _gate=_require_custom_fields
) -> ApplyTemplateResponse:
    template = await custom_fields_service.get_template(session, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    result = await custom_fields_service.apply_template(
        session, tenant_id=context.tenant_id, template=template
    )
    await commit_and_keep_tenant_context(session)
    return result
