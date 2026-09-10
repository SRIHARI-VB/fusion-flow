"""Custom-fields domain logic.

None of these functions commit - routers own the transaction boundary (via
`db.session.commit_and_keep_tenant_context`), matching the convention in
`modules/tenancy/service.py`.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.custom_fields.models import EntityType, FieldDefinition, FieldTemplate
from fusionflow.modules.custom_fields.schemas import (
    ApplyTemplateResponse,
    FieldDefinitionCreate,
    FieldDefinitionOut,
    FieldDefinitionUpdate,
)


async def list_field_definitions(
    session: AsyncSession, *, tenant_id: uuid.UUID, entity_type: EntityType | None = None
) -> Sequence[FieldDefinition]:
    stmt = select(FieldDefinition).where(FieldDefinition.tenant_id == tenant_id)
    if entity_type is not None:
        stmt = stmt.where(FieldDefinition.entity_type == entity_type)
    stmt = stmt.order_by(FieldDefinition.entity_type, FieldDefinition.sort_order, FieldDefinition.key)
    return (await session.execute(stmt)).scalars().all()


async def count_field_definitions(
    session: AsyncSession, tenant_id: uuid.UUID, *, entity_type: EntityType
) -> int:
    """Field definitions for one entity_type only - the configured
    `custom_fields` limit applies independently per entity_type (a limit
    of 10 means up to 10 Product fields AND up to 10 Service fields AND so
    on, not 10 shared across all of them), since each entity_type's custom
    fields are otherwise unrelated to each other."""
    stmt = select(func.count()).select_from(FieldDefinition).where(
        FieldDefinition.tenant_id == tenant_id, FieldDefinition.entity_type == entity_type
    )
    return (await session.execute(stmt)).scalar_one()


async def get_field_definition(
    session: AsyncSession, *, tenant_id: uuid.UUID, definition_id: uuid.UUID
) -> FieldDefinition | None:
    return (
        await session.execute(
            select(FieldDefinition).where(
                FieldDefinition.id == definition_id, FieldDefinition.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()


async def create_field_definition(
    session: AsyncSession, *, tenant_id: uuid.UUID, payload: FieldDefinitionCreate
) -> FieldDefinition:
    definition = FieldDefinition(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        entity_type=payload.entity_type,
        key=payload.key,
        label=payload.label,
        field_type=payload.field_type,
        options=payload.options,
        required=payload.required,
        sort_order=payload.sort_order,
    )
    session.add(definition)
    await session.flush()
    return definition


async def update_field_definition(
    session: AsyncSession, definition: FieldDefinition, payload: FieldDefinitionUpdate
) -> FieldDefinition:
    if payload.label is not None:
        definition.label = payload.label
    if payload.options is not None:
        definition.options = payload.options
    if payload.required is not None:
        definition.required = payload.required
    if payload.sort_order is not None:
        definition.sort_order = payload.sort_order
    await session.flush()
    return definition


async def delete_field_definition(session: AsyncSession, definition: FieldDefinition) -> None:
    await session.delete(definition)
    await session.flush()


async def list_templates(
    session: AsyncSession, *, vertical: str | None = None, entity_type: EntityType | None = None
) -> Sequence[FieldTemplate]:
    stmt = select(FieldTemplate)
    if vertical is not None:
        stmt = stmt.where(FieldTemplate.vertical == vertical)
    if entity_type is not None:
        stmt = stmt.where(FieldTemplate.entity_type == entity_type)
    stmt = stmt.order_by(FieldTemplate.vertical, FieldTemplate.entity_type, FieldTemplate.name)
    return (await session.execute(stmt)).scalars().all()


async def get_template(session: AsyncSession, template_id: uuid.UUID) -> FieldTemplate | None:
    return await session.get(FieldTemplate, template_id)


async def apply_template(
    session: AsyncSession, *, tenant_id: uuid.UUID, template: FieldTemplate
) -> ApplyTemplateResponse:
    """Copy a template's field set into the tenant's own `field_definitions`.

    A one-time copy, not a live link (see the module docstring). Any key the
    tenant already has for this entity_type is skipped rather than raising,
    so re-applying the same template - or applying two overlapping ones - is
    always safe to call.
    """
    existing_keys = {
        d.key
        for d in await list_field_definitions(session, tenant_id=tenant_id, entity_type=template.entity_type)
    }
    created: list[FieldDefinition] = []
    skipped: list[str] = []
    for spec in template.fields:
        key = spec["key"]
        if key in existing_keys:
            skipped.append(key)
            continue
        definition = FieldDefinition(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            entity_type=template.entity_type,
            key=key,
            label=spec["label"],
            field_type=spec["field_type"],
            options=spec.get("options"),
            required=spec.get("required", False),
            sort_order=spec.get("sort_order", 0),
            source_template_id=template.id,
        )
        session.add(definition)
        created.append(definition)
        existing_keys.add(key)
    await session.flush()
    return ApplyTemplateResponse(
        created=[FieldDefinitionOut.model_validate(d) for d in created],
        skipped_existing_keys=skipped,
    )
