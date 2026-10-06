"""`/api/v1/business-objects` - tenant-defined custom business object types
(e.g. "Delivery", "Appointment") and their generic records.

No router-level `require_module_access` gate (unlike every fixed module's
router): generic object types are tenant-owned metadata, not a platform
feature toggle - see `workflow_adapter.py` for why the workflow side also
treats them as always available. The ONE exception is the `appointment`
object type, which the frontend Appointments module reads/writes through
these generic routes: any request that touches that type (by id, by key, or
via one of its records/fields) is gated in-handler by
`_ensure_appointments_access` with `require_module_access("appointments")`,
so a super-admin revoke or role restriction closes the API, not just the UI.
`GET /types` stays open (it lists metadata, and Settings/clinic_queue need
it). clinic_queue uses the service layer directly, so it is unaffected.

Not mounted here - see `api.py`'s docstring; mount `router` from this
module under the `/api/v1` group.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.business_objects import service as business_objects_service
from fusionflow.modules.business_objects.models import ObjectTypeDefinition
from fusionflow.modules.connectors.deps import require_module_access
from fusionflow.modules.business_objects.schemas import (
    ObjectFieldDefinitionCreate,
    ObjectFieldDefinitionOut,
    ObjectFieldDefinitionUpdate,
    ObjectRecordCreate,
    ObjectRecordOut,
    ObjectRecordUpdate,
    ObjectTypeCreate,
    ObjectTypeOut,
    ObjectTypeUpdate,
)

router = APIRouter(prefix="/business-objects", tags=["business-objects"])

APPOINTMENT_TYPE_KEY = "appointment"
_appointments_gate = require_module_access("appointments")


async def _ensure_appointments_access(context: TenantContextDep, session: SessionDep, type_key: str) -> None:
    """Raise 403 unless the tenant/role may use the Appointments module,
    but only when `type_key` is the appointment object type."""
    if type_key == APPOINTMENT_TYPE_KEY:
        await _appointments_gate(context, session)


_TYPE_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Object type not found")
_FIELD_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field definition not found")
_RECORD_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Record not found")


async def _get_type_or_404(
    session: SessionDep, tenant_id: uuid.UUID, type_id: uuid.UUID, context: TenantContextDep | None = None
) -> ObjectTypeDefinition:
    object_type = await business_objects_service.get_object_type(
        session, tenant_id=tenant_id, object_type_id=type_id
    )
    if object_type is None:
        raise _TYPE_NOT_FOUND
    if context is not None:
        await _ensure_appointments_access(context, session, object_type.key)
    return object_type


async def _get_type_by_key_or_404(
    session: SessionDep, tenant_id: uuid.UUID, key: str, context: TenantContextDep | None = None
) -> ObjectTypeDefinition:
    if context is not None:
        await _ensure_appointments_access(context, session, key)
    object_type = await business_objects_service.get_object_type_by_key(session, tenant_id=tenant_id, key=key)
    if object_type is None:
        raise _TYPE_NOT_FOUND
    return object_type


# ---------------------------------------------------------------------------
# Object types
# ---------------------------------------------------------------------------


@router.get("/types", response_model=list[ObjectTypeOut])
async def list_object_types(context: TenantContextDep, session: SessionDep) -> list[ObjectTypeOut]:
    types = await business_objects_service.list_object_types(session, tenant_id=context.tenant_id)
    return [ObjectTypeOut.model_validate(t) for t in types]


@router.post("/types", response_model=ObjectTypeOut, status_code=status.HTTP_201_CREATED)
async def create_object_type(
    payload: ObjectTypeCreate, context: TenantContextDep, session: SessionDep
) -> ObjectTypeOut:
    await _ensure_appointments_access(context, session, payload.key)
    existing = await business_objects_service.get_object_type_by_key(
        session, tenant_id=context.tenant_id, key=payload.key
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"object type key {payload.key!r} already exists"
        )
    object_type = await business_objects_service.create_object_type(
        session, tenant_id=context.tenant_id, payload=payload
    )
    await commit_and_keep_tenant_context(session)
    return ObjectTypeOut.model_validate(object_type)


@router.get("/types/{type_id}", response_model=ObjectTypeOut)
async def get_object_type(type_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> ObjectTypeOut:
    object_type = await _get_type_or_404(session, context.tenant_id, type_id, context)
    return ObjectTypeOut.model_validate(object_type)


@router.patch("/types/{type_id}", response_model=ObjectTypeOut)
async def update_object_type(
    type_id: uuid.UUID, payload: ObjectTypeUpdate, context: TenantContextDep, session: SessionDep
) -> ObjectTypeOut:
    object_type = await _get_type_or_404(session, context.tenant_id, type_id, context)
    object_type = await business_objects_service.update_object_type(session, object_type, payload)
    await commit_and_keep_tenant_context(session)
    # `updated_at` is DB-computed (`onupdate=func.now()`) and left expired
    # after an UPDATE flush - see `predefined_automations/router.py`'s
    # identical fix for the full explanation of the MissingGreenlet crash
    # this avoids.
    await session.refresh(object_type, attribute_names=["updated_at"])
    return ObjectTypeOut.model_validate(object_type)


@router.delete("/types/{type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_object_type(type_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> None:
    object_type = await _get_type_or_404(session, context.tenant_id, type_id, context)
    await business_objects_service.delete_object_type(session, object_type)
    await commit_and_keep_tenant_context(session)


# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------


@router.get("/types/{type_id}/fields", response_model=list[ObjectFieldDefinitionOut])
async def list_field_definitions(
    type_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> list[ObjectFieldDefinitionOut]:
    await _get_type_or_404(session, context.tenant_id, type_id, context)
    fields = await business_objects_service.list_field_definitions(
        session, tenant_id=context.tenant_id, object_type_id=type_id
    )
    return [ObjectFieldDefinitionOut.model_validate(f) for f in fields]


@router.post(
    "/types/{type_id}/fields", response_model=ObjectFieldDefinitionOut, status_code=status.HTTP_201_CREATED
)
async def create_field_definition(
    type_id: uuid.UUID, payload: ObjectFieldDefinitionCreate, context: TenantContextDep, session: SessionDep
) -> ObjectFieldDefinitionOut:
    await _get_type_or_404(session, context.tenant_id, type_id, context)
    field_definition = await business_objects_service.create_field_definition(
        session, tenant_id=context.tenant_id, object_type_id=type_id, payload=payload
    )
    await commit_and_keep_tenant_context(session)
    return ObjectFieldDefinitionOut.model_validate(field_definition)


@router.patch("/types/{type_id}/fields/{field_id}", response_model=ObjectFieldDefinitionOut)
async def update_field_definition(
    type_id: uuid.UUID,
    field_id: uuid.UUID,
    payload: ObjectFieldDefinitionUpdate,
    context: TenantContextDep,
    session: SessionDep,
) -> ObjectFieldDefinitionOut:
    await _get_type_or_404(session, context.tenant_id, type_id, context)
    field_definition = await business_objects_service.get_field_definition(
        session, tenant_id=context.tenant_id, field_id=field_id
    )
    if field_definition is None or field_definition.object_type_id != type_id:
        raise _FIELD_NOT_FOUND
    field_definition = await business_objects_service.update_field_definition(session, field_definition, payload)
    await commit_and_keep_tenant_context(session)
    return ObjectFieldDefinitionOut.model_validate(field_definition)


@router.delete("/types/{type_id}/fields/{field_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_field_definition(
    type_id: uuid.UUID, field_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> None:
    await _get_type_or_404(session, context.tenant_id, type_id, context)
    field_definition = await business_objects_service.get_field_definition(
        session, tenant_id=context.tenant_id, field_id=field_id
    )
    if field_definition is None or field_definition.object_type_id != type_id:
        raise _FIELD_NOT_FOUND
    await business_objects_service.delete_field_definition(session, field_definition)
    await commit_and_keep_tenant_context(session)


async def _ensure_record_access(context: TenantContextDep, session: SessionDep, record) -> None:
    object_type = await business_objects_service.get_object_type(
        session, tenant_id=context.tenant_id, object_type_id=record.object_type_id
    )
    if object_type is not None:
        await _ensure_appointments_access(context, session, object_type.key)


# ---------------------------------------------------------------------------
# Records - addressed by the type's `key` (slug), matching the module-picker
# identifier a workflow node's `config.module` also uses.
# ---------------------------------------------------------------------------


@router.get("/types/{key}/records", response_model=list[ObjectRecordOut])
async def list_records(key: str, context: TenantContextDep, session: SessionDep) -> list[ObjectRecordOut]:
    object_type = await _get_type_by_key_or_404(session, context.tenant_id, key, context)
    records = await business_objects_service.list_records(
        session, tenant_id=context.tenant_id, object_type_id=object_type.id
    )
    return [ObjectRecordOut.model_validate(r) for r in records]


@router.post("/types/{key}/records", response_model=ObjectRecordOut, status_code=status.HTTP_201_CREATED)
async def create_record(
    key: str, payload: ObjectRecordCreate, context: TenantContextDep, session: SessionDep
) -> ObjectRecordOut:
    object_type = await _get_type_by_key_or_404(session, context.tenant_id, key, context)
    field_defs = await business_objects_service.list_field_definitions(
        session, tenant_id=context.tenant_id, object_type_id=object_type.id
    )
    record = await business_objects_service.create_record(
        session,
        tenant_id=context.tenant_id,
        object_type=object_type,
        field_defs=field_defs,
        payload=payload.payload,
        customer_id=payload.customer_id,
    )
    await commit_and_keep_tenant_context(session)
    return ObjectRecordOut.model_validate(record)


@router.get("/records/{record_id}", response_model=ObjectRecordOut)
async def get_record(record_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> ObjectRecordOut:
    record = await business_objects_service.get_record(session, tenant_id=context.tenant_id, record_id=record_id)
    if record is None:
        raise _RECORD_NOT_FOUND
    await _ensure_record_access(context, session, record)
    return ObjectRecordOut.model_validate(record)


@router.patch("/records/{record_id}", response_model=ObjectRecordOut)
async def update_record(
    record_id: uuid.UUID, payload: ObjectRecordUpdate, context: TenantContextDep, session: SessionDep
) -> ObjectRecordOut:
    record = await business_objects_service.get_record(session, tenant_id=context.tenant_id, record_id=record_id)
    if record is None:
        raise _RECORD_NOT_FOUND
    await _ensure_record_access(context, session, record)
    field_defs = await business_objects_service.list_field_definitions(
        session, tenant_id=context.tenant_id, object_type_id=record.object_type_id
    )
    record = await business_objects_service.update_record(
        session, record, field_defs=field_defs, payload=payload.payload, customer_id=payload.customer_id
    )
    await commit_and_keep_tenant_context(session)
    # Same `updated_at` refresh as `update_object_type` above.
    await session.refresh(record, attribute_names=["updated_at"])
    return ObjectRecordOut.model_validate(record)


@router.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_record(record_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> None:
    record = await business_objects_service.get_record(session, tenant_id=context.tenant_id, record_id=record_id)
    if record is None:
        raise _RECORD_NOT_FOUND
    await _ensure_record_access(context, session, record)
    await business_objects_service.delete_record(session, record)
    await commit_and_keep_tenant_context(session)
