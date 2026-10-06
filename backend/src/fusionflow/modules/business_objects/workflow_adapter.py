"""Custom Business Object module's workflow-engine bridge.

Deliberately NOT a `ModuleQueryAdapter` registered into
`engine.module_registry.registry` the way every fixed module's adapter is
(see `catalog/workflow_adapter.py`): that registry is a process-wide,
non-tenant-scoped singleton keyed by a bare `module_key` string.
Registering one tenant's object-type key into it would either leak across
tenants (any tenant's workflow could suddenly see another tenant's
"delivery" module) or collide outright if two tenants happen to pick the
same key. Both are real multi-tenant correctness bugs, not style concerns.

Instead, `nodes/module_list.py`/`module_get.py`/`module_create.py`/
`module_update.py` call `resolve()` directly, once per node execution,
*after* the global registry's `get_or_none` has already missed - so a
tenant-defined object type is reachable the moment it exists, with no
process restart and no cross-tenant leakage, at the cost of one extra
per-request lookup instead of an in-memory dict hit.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.business_objects import service as business_objects_service
from fusionflow.modules.business_objects.models import ObjectTypeDefinition
from fusionflow.modules.business_objects.schemas import ObjectRecordOut
from fusionflow.modules.workflows.engine.module_registry import ModuleQueryAdapter


class CustomObjectQueryAdapter(ModuleQueryAdapter):
    """One-shot, per-request adapter bound to a single resolved
    `ObjectTypeDefinition` - constructed fresh by `resolve()` on every
    call, never cached, so it always reflects that type's current field
    definitions. `list`'s `filters` supports only `customer_id` in this
    first pass (no arbitrary JSONB-field filtering yet).

    Domain validation failures (`business_objects_service.
    validate_record_payload` raising `HTTPException`, the same convention
    `catalog.service.validate_entity_custom_fields` uses) are translated to
    a plain `ValueError` here - the workflow-facing boundary already has an
    established convention of signalling domain errors via `ValueError`
    (see `orders/workflow_adapter.py`'s "only status field" rejection),
    which `module_create.py`/`module_update.py` already know how to turn
    into a clean `Failure` instead of crashing the run.
    """

    def __init__(self, object_type: ObjectTypeDefinition) -> None:
        self.object_type = object_type
        self.module_key = object_type.key
        self.created_by_run_id: uuid.UUID | None = None

    async def list(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        customer_id = filters.get("customer_id")
        items = await business_objects_service.list_records(
            session,
            tenant_id=tenant_id,
            object_type_id=self.object_type.id,
            customer_id=uuid.UUID(str(customer_id)) if customer_id else None,
            limit=limit,
        )
        return [ObjectRecordOut.model_validate(item).model_dump(mode="json") for item in items]

    async def get(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> dict[str, Any] | None:
        item = await business_objects_service.get_record(session, tenant_id=tenant_id, record_id=item_id)
        if item is None or item.object_type_id != self.object_type.id:
            return None
        return ObjectRecordOut.model_validate(item).model_dump(mode="json")

    async def create(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any]:
        field_defs = await business_objects_service.list_field_definitions(
            session, tenant_id=tenant_id, object_type_id=self.object_type.id
        )
        fields = dict(fields)
        customer_id = fields.pop("customer_id", None)
        try:
            item = await business_objects_service.create_record(
                session,
                tenant_id=tenant_id,
                object_type=self.object_type,
                field_defs=field_defs,
                payload=fields,
                customer_id=uuid.UUID(str(customer_id)) if customer_id else None,
                created_by_run_id=self.created_by_run_id,
            )
        except HTTPException as exc:
            raise ValueError(_flatten_detail(exc)) from exc
        return ObjectRecordOut.model_validate(item).model_dump(mode="json")

    async def update(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        item = await business_objects_service.get_record(session, tenant_id=tenant_id, record_id=item_id)
        if item is None or item.object_type_id != self.object_type.id:
            return None
        field_defs = await business_objects_service.list_field_definitions(
            session, tenant_id=tenant_id, object_type_id=self.object_type.id
        )
        fields = dict(fields)
        customer_id = fields.pop("customer_id", None)
        try:
            updated = await business_objects_service.update_record(
                session,
                item,
                field_defs=field_defs,
                payload=fields or None,
                customer_id=uuid.UUID(str(customer_id)) if customer_id else None,
            )
        except HTTPException as exc:
            raise ValueError(_flatten_detail(exc)) from exc
        # `updated_at`'s `onupdate=func.now()` is a server-side expression -
        # SQLAlchemy can't know the resulting value client-side, so it
        # marks the attribute expired after the flush inside
        # `update_record`. `ObjectRecordOut.model_validate` below reads
        # attributes synchronously (Pydantic validation, not itself
        # awaited); accessing an expired attribute there tries an implicit
        # lazy-refresh with no active greenlet bridge to run it through,
        # raising `MissingGreenlet` (confirmed live - this update path had
        # never been exercised by a real caller until a workflow's
        # duplicate-appointment-cancel step hit it). An explicit, awaited
        # refresh first avoids the implicit one.
        await session.refresh(updated)
        return ObjectRecordOut.model_validate(updated).model_dump(mode="json")


def _flatten_detail(exc: HTTPException) -> str:
    detail = exc.detail
    if isinstance(detail, dict):
        return str(detail.get("message") or detail)
    return str(detail)


async def resolve(session: AsyncSession, *, tenant_id: uuid.UUID, key: str) -> CustomObjectQueryAdapter | None:
    """Look up a tenant-defined object type by its module-picker key.
    Returns `None` if no such (active) type exists for this tenant - the
    caller (a `module.*` node) then reports "unknown module", exactly like
    it would for a typo'd fixed-module key."""
    object_type = await business_objects_service.get_object_type_by_key(session, tenant_id=tenant_id, key=key)
    if object_type is None or not object_type.is_active:
        return None
    return CustomObjectQueryAdapter(object_type)
