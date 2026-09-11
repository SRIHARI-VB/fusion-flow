"""Business-objects domain logic: tenant-defined object types, their field
definitions, and generic records against them.

None of these functions commit - routers (and the workflow-node fallback in
`workflow_adapter.py`) own the transaction boundary, same convention as
every other module's `service.py` in this codebase.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.business_objects.models import ObjectFieldDefinition, ObjectRecord, ObjectTypeDefinition
from fusionflow.modules.business_objects.schemas import (
    ObjectFieldDefinitionCreate,
    ObjectFieldDefinitionUpdate,
    ObjectTypeCreate,
    ObjectTypeUpdate,
)
from fusionflow.modules.custom_fields.validation import CustomFieldValidationError, validate_custom_fields

# ---------------------------------------------------------------------------
# ObjectTypeDefinition
# ---------------------------------------------------------------------------


async def list_object_types(
    session: AsyncSession, *, tenant_id: uuid.UUID, is_active: bool | None = None
) -> Sequence[ObjectTypeDefinition]:
    stmt = select(ObjectTypeDefinition).where(ObjectTypeDefinition.tenant_id == tenant_id)
    if is_active is not None:
        stmt = stmt.where(ObjectTypeDefinition.is_active == is_active)
    stmt = stmt.order_by(ObjectTypeDefinition.name)
    return (await session.execute(stmt)).scalars().all()


async def get_object_type(
    session: AsyncSession, *, tenant_id: uuid.UUID, object_type_id: uuid.UUID
) -> ObjectTypeDefinition | None:
    return (
        await session.execute(
            select(ObjectTypeDefinition).where(
                ObjectTypeDefinition.id == object_type_id, ObjectTypeDefinition.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()


async def get_object_type_by_key(
    session: AsyncSession, *, tenant_id: uuid.UUID, key: str
) -> ObjectTypeDefinition | None:
    """The module-picker lookup: resolves a tenant's own object type by its
    slug (`key`), the same identifier a workflow's `module.*` node config
    carries - see `workflow_adapter.resolve`."""
    return (
        await session.execute(
            select(ObjectTypeDefinition).where(
                ObjectTypeDefinition.key == key, ObjectTypeDefinition.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()


async def create_object_type(
    session: AsyncSession, *, tenant_id: uuid.UUID, payload: ObjectTypeCreate
) -> ObjectTypeDefinition:
    object_type = ObjectTypeDefinition(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        key=payload.key,
        name=payload.name,
        icon=payload.icon,
        description=payload.description,
        is_active=payload.is_active,
    )
    session.add(object_type)
    await session.flush()
    return object_type


async def update_object_type(
    session: AsyncSession, object_type: ObjectTypeDefinition, payload: ObjectTypeUpdate
) -> ObjectTypeDefinition:
    if payload.name is not None:
        object_type.name = payload.name
    if payload.icon is not None:
        object_type.icon = payload.icon
    if payload.description is not None:
        object_type.description = payload.description
    if payload.is_active is not None:
        object_type.is_active = payload.is_active
    await session.flush()
    return object_type


async def delete_object_type(session: AsyncSession, object_type: ObjectTypeDefinition) -> None:
    """Deletes the type and, via `ON DELETE CASCADE`, every field
    definition and record that belongs to it - no separate "is it in use"
    guard, matching `catalog.service.delete_product_service`'s equally
    unconditional delete."""
    await session.delete(object_type)
    await session.flush()


# ---------------------------------------------------------------------------
# ObjectFieldDefinition
# ---------------------------------------------------------------------------


async def list_field_definitions(
    session: AsyncSession, *, tenant_id: uuid.UUID, object_type_id: uuid.UUID
) -> Sequence[ObjectFieldDefinition]:
    stmt = (
        select(ObjectFieldDefinition)
        .where(
            ObjectFieldDefinition.tenant_id == tenant_id,
            ObjectFieldDefinition.object_type_id == object_type_id,
        )
        .order_by(ObjectFieldDefinition.sort_order, ObjectFieldDefinition.key)
    )
    return (await session.execute(stmt)).scalars().all()


async def get_field_definition(
    session: AsyncSession, *, tenant_id: uuid.UUID, field_id: uuid.UUID
) -> ObjectFieldDefinition | None:
    return (
        await session.execute(
            select(ObjectFieldDefinition).where(
                ObjectFieldDefinition.id == field_id, ObjectFieldDefinition.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()


async def create_field_definition(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    object_type_id: uuid.UUID,
    payload: ObjectFieldDefinitionCreate,
) -> ObjectFieldDefinition:
    field_definition = ObjectFieldDefinition(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type_id=object_type_id,
        key=payload.key,
        label=payload.label,
        field_type=payload.field_type,
        options=payload.options,
        required=payload.required,
        sort_order=payload.sort_order,
    )
    session.add(field_definition)
    await session.flush()
    return field_definition


async def update_field_definition(
    session: AsyncSession, field_definition: ObjectFieldDefinition, payload: ObjectFieldDefinitionUpdate
) -> ObjectFieldDefinition:
    if payload.label is not None:
        field_definition.label = payload.label
    if payload.options is not None:
        field_definition.options = payload.options
    if payload.required is not None:
        field_definition.required = payload.required
    if payload.sort_order is not None:
        field_definition.sort_order = payload.sort_order
    await session.flush()
    return field_definition


async def delete_field_definition(session: AsyncSession, field_definition: ObjectFieldDefinition) -> None:
    await session.delete(field_definition)
    await session.flush()


# ---------------------------------------------------------------------------
# Record payload validation
# ---------------------------------------------------------------------------


def validate_record_payload(
    field_defs: Sequence[ObjectFieldDefinition], payload: dict[str, Any] | None
) -> dict[str, Any]:
    """Shared write-path guard for `ObjectRecord.payload`, mirroring
    `catalog.service.validate_entity_custom_fields` exactly: reuses
    `custom_fields.validation.validate_custom_fields` directly rather than
    reimplementing type/required/option checking, since that function is
    duck-typed against `.key`/`.field_type`/`.required`/`.options` and
    `ObjectFieldDefinition` has that exact shape.
    """
    try:
        return validate_custom_fields(list(field_defs), payload)
    except CustomFieldValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "record payload validation failed", "errors": exc.errors},
        ) from exc


# ---------------------------------------------------------------------------
# ObjectRecord
# ---------------------------------------------------------------------------


async def list_records(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    object_type_id: uuid.UUID,
    customer_id: uuid.UUID | None = None,
    limit: int | None = None,
) -> Sequence[ObjectRecord]:
    stmt = select(ObjectRecord).where(
        ObjectRecord.tenant_id == tenant_id, ObjectRecord.object_type_id == object_type_id
    )
    if customer_id is not None:
        stmt = stmt.where(ObjectRecord.customer_id == customer_id)
    stmt = stmt.order_by(ObjectRecord.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return (await session.execute(stmt)).scalars().all()


async def get_record(session: AsyncSession, *, tenant_id: uuid.UUID, record_id: uuid.UUID) -> ObjectRecord | None:
    return (
        await session.execute(
            select(ObjectRecord).where(ObjectRecord.id == record_id, ObjectRecord.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def create_record(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    object_type: ObjectTypeDefinition,
    field_defs: Sequence[ObjectFieldDefinition],
    payload: dict[str, Any] | None,
    customer_id: uuid.UUID | None = None,
    created_by_run_id: uuid.UUID | None = None,
) -> ObjectRecord:
    validated = validate_record_payload(field_defs, payload)
    record = ObjectRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type_id=object_type.id,
        payload=validated,
        customer_id=customer_id,
        created_by_run_id=created_by_run_id,
    )
    session.add(record)
    await session.flush()
    return record


async def update_record(
    session: AsyncSession,
    record: ObjectRecord,
    *,
    field_defs: Sequence[ObjectFieldDefinition],
    payload: dict[str, Any] | None = None,
    customer_id: uuid.UUID | None = None,
) -> ObjectRecord:
    """Partial update: `payload`, when given, is merged into the record's
    existing payload (not a wholesale replace) before re-validation, so a
    caller can patch just the fields it knows about."""
    if payload is not None:
        merged = {**record.payload, **payload}
        record.payload = validate_record_payload(field_defs, merged)
    if customer_id is not None:
        record.customer_id = customer_id
    await session.flush()
    return record


async def delete_record(session: AsyncSession, record: ObjectRecord) -> None:
    await session.delete(record)
    await session.flush()
