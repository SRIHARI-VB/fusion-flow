"""Generic CRUD + REST router for a fixed module's own field-definition table.

Every table built on `ModuleFieldDefinitionMixin` (see `models.py`) has the
exact same shape (`id`, `tenant_id`, `key`, `label`, `field_type`, `options`,
`required`, `sort_order`) and the exact same CRUD semantics
(`business_objects.service`'s `*_field_definition` functions and
`custom_fields.service`'s `*_field_definition` functions were two
hand-written, near-identical copies of this before this module existed).
This is the one place that logic lives now: a module that wants tenant-
defined custom fields declares its own table (mixing in
`ModuleFieldDefinitionMixin`) and mounts `make_field_definitions_router`
against it, instead of re-implementing list/get/create/update/delete and
the four request/response schemas again.

Field-*value* validation (checking a `custom_fields` JSONB payload against
these definitions at write time) is a separate concern, already generic:
`custom_fields.validation.validate_custom_fields`.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol, Sequence, TypeVar

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.custom_fields.models import FieldType

# Lowercase snake_case, must start with a letter - same convention as
# `custom_fields.schemas._KEY_PATTERN` / `business_objects.schemas._KEY_PATTERN`.
_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"


class ModuleFieldDefinitionCreate(BaseModel):
    key: str = Field(min_length=1, max_length=100, pattern=_KEY_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    field_type: FieldType
    options: list[Any] | None = None
    required: bool = False
    sort_order: int = 0

    @field_validator("options")
    @classmethod
    def _options_required_for_choice_types(cls, value: list[Any] | None, info: Any) -> list[Any] | None:
        field_type = info.data.get("field_type")
        if field_type in (FieldType.SELECT, FieldType.MULTISELECT) and not value:
            raise ValueError("options is required for select/multiselect fields")
        return value


class ModuleFieldDefinitionUpdate(BaseModel):
    """Partial update. `key`/`field_type` are immutable after creation - same
    "delete and recreate to change shape" convention as
    `custom_fields.schemas.FieldDefinitionUpdate`."""

    label: str | None = Field(default=None, min_length=1, max_length=200)
    options: list[Any] | None = None
    required: bool | None = None
    sort_order: int | None = None


class ModuleFieldDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    label: str
    field_type: FieldType
    options: list[Any] | None
    required: bool
    sort_order: int


class _ModuleFieldDefinitionRow(Protocol):
    """The attribute shape `make_field_definitions_router` needs from a model
    class - satisfied by any `Base, TenantScopedMixin, ModuleFieldDefinitionMixin` model."""

    id: Any
    tenant_id: Any
    key: Any
    label: Any
    field_type: Any
    options: Any
    required: Any
    sort_order: Any


ModelT = TypeVar("ModelT", bound=_ModuleFieldDefinitionRow)


async def list_definitions(session: AsyncSession, model: type[ModelT], *, tenant_id: uuid.UUID) -> Sequence[ModelT]:
    stmt = select(model).where(model.tenant_id == tenant_id).order_by(model.sort_order, model.key)
    return (await session.execute(stmt)).scalars().all()


async def get_definition(
    session: AsyncSession, model: type[ModelT], *, tenant_id: uuid.UUID, definition_id: uuid.UUID
) -> ModelT | None:
    return (
        await session.execute(
            select(model).where(model.id == definition_id, model.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def create_definition(
    session: AsyncSession, model: type[ModelT], *, tenant_id: uuid.UUID, payload: ModuleFieldDefinitionCreate
) -> ModelT:
    definition = model(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
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


async def update_definition(
    session: AsyncSession, definition: ModelT, payload: ModuleFieldDefinitionUpdate
) -> ModelT:
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


async def delete_definition(session: AsyncSession, definition: ModelT) -> None:
    await session.delete(definition)
    await session.flush()


def make_field_definitions_router(
    *, path: str, tags: list[str], model: type[_ModuleFieldDefinitionRow], gate: Any | None = None
) -> APIRouter:
    """Build a `field-definitions` sub-router for one fixed module's table.

    `path` is mounted as-is (e.g. `/customers/field-definitions`) rather than
    composed from a prefix, since callers already have their own router
    mounted at the module's own prefix and this is a sibling, not a child, of
    it. `gate`, when given, is a FastAPI dependency (e.g.
    `Depends(require_module_access("customers"))`) applied to every route -
    the same entitlement gate the module's own router already uses, so a
    tenant without access to a module can't see or edit its custom fields
    either.
    """

    router = APIRouter(tags=tags, dependencies=[gate] if gate is not None else [])
    not_found = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field definition not found")

    @router.get(path, response_model=list[ModuleFieldDefinitionOut])
    async def list_(context: TenantContextDep, session: SessionDep) -> list[ModuleFieldDefinitionOut]:
        definitions = await list_definitions(session, model, tenant_id=context.tenant_id)
        return [ModuleFieldDefinitionOut.model_validate(d) for d in definitions]

    @router.post(path, response_model=ModuleFieldDefinitionOut, status_code=status.HTTP_201_CREATED)
    async def create_(
        payload: ModuleFieldDefinitionCreate, context: TenantContextDep, session: SessionDep
    ) -> ModuleFieldDefinitionOut:
        definition = await create_definition(session, model, tenant_id=context.tenant_id, payload=payload)
        await commit_and_keep_tenant_context(session)
        return ModuleFieldDefinitionOut.model_validate(definition)

    @router.patch(f"{path}/{{definition_id}}", response_model=ModuleFieldDefinitionOut)
    async def update_(
        definition_id: uuid.UUID,
        payload: ModuleFieldDefinitionUpdate,
        context: TenantContextDep,
        session: SessionDep,
    ) -> ModuleFieldDefinitionOut:
        definition = await get_definition(session, model, tenant_id=context.tenant_id, definition_id=definition_id)
        if definition is None:
            raise not_found
        definition = await update_definition(session, definition, payload)
        await commit_and_keep_tenant_context(session)
        return ModuleFieldDefinitionOut.model_validate(definition)

    @router.delete(f"{path}/{{definition_id}}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_(definition_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> None:
        definition = await get_definition(session, model, tenant_id=context.tenant_id, definition_id=definition_id)
        if definition is None:
            raise not_found
        await delete_definition(session, definition)
        await commit_and_keep_tenant_context(session)

    return router
