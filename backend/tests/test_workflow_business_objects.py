"""Tests for the Custom Business Object module (composable-workflow-builder
redesign, Phase 2): tenant-defined object types/fields/records, and the
runtime fallback that lets a workflow's `module.list`/`module.get`/
`module.create`/`module.update` reach a tenant's own object type without a
global registry entry (see `business_objects/workflow_adapter.py`'s module
docstring).

Split the same way `test_workflow_module_nodes.py`/`test_orders_service.py`
are:

* Offline tests (default, no Postgres) - `validate_record_payload` is a
  pure function reused from `custom_fields.validation`; `create_record`/
  `update_record`/`delete_record` never `SELECT` (they're handed an
  already-resolved row), so a `_FakeSession` stand-in (same shape as
  `test_orders_service.py`'s) exercises them fully; the node-level fallback
  wiring is exercised by monkeypatching `business_objects_workflow_adapter.
  resolve` exactly like the existing tests monkeypatch `module_registry.
  get_or_none`.
* `requires_postgres` tests - full type/field/record CRUD round-trips and
  cross-tenant isolation need real `SELECT`s against RLS-enabled tables;
  they skip (not fail) without `$TEST_DATABASE_URL`, same as
  `test_rls_isolation.py`.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import HTTPException

from fusionflow.modules.business_objects import service as business_objects_service
from fusionflow.modules.business_objects import workflow_adapter as business_objects_workflow_adapter
from fusionflow.modules.business_objects.models import ObjectFieldDefinition, ObjectRecord, ObjectTypeDefinition
from fusionflow.modules.custom_fields.models import FieldType
from fusionflow.modules.workflows.engine import module_registry
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.nodes import module_create as module_create_node
from fusionflow.modules.workflows.nodes import module_get as module_get_node
from fusionflow.modules.workflows.nodes import module_list as module_list_node
from fusionflow.modules.workflows.nodes import module_update as module_update_node

from tests.conftest import requires_postgres

_TENANT_ID = uuid.uuid4()


def _field(key: str, field_type: FieldType, *, required: bool = False, options=None) -> ObjectFieldDefinition:
    return ObjectFieldDefinition(
        id=uuid.uuid4(),
        tenant_id=_TENANT_ID,
        object_type_id=uuid.uuid4(),
        key=key,
        label=key,
        field_type=field_type,
        options=options,
        required=required,
        sort_order=0,
    )


def _object_type(*, key: str = "delivery", is_active: bool = True) -> ObjectTypeDefinition:
    return ObjectTypeDefinition(
        id=uuid.uuid4(), tenant_id=_TENANT_ID, key=key, name=key.title(), is_active=is_active
    )


class _FakeSession:
    """Mirrors `test_orders_service.py`'s `_FakeSession` - only `add`/
    `flush`, no `execute`, matching every function under test here that is
    handed an already-resolved row rather than looking one up itself."""

    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


# ---------------------------------------------------------------------------
# validate_record_payload
# ---------------------------------------------------------------------------


def test_validate_record_payload_accepts_a_valid_payload() -> None:
    field_defs = [_field("notes", FieldType.TEXT, required=True), _field("priority", FieldType.NUMBER)]
    result = business_objects_service.validate_record_payload(field_defs, {"notes": "ring the bell", "priority": 2})
    assert result == {"notes": "ring the bell", "priority": 2.0}


def test_validate_record_payload_rejects_missing_required_field() -> None:
    field_defs = [_field("address", FieldType.TEXT, required=True)]
    with pytest.raises(HTTPException) as exc_info:
        business_objects_service.validate_record_payload(field_defs, {})
    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["message"] == "record payload validation failed"


def test_validate_record_payload_rejects_invalid_select_option() -> None:
    field_defs = [_field("slot", FieldType.SELECT, options=["morning", "evening"])]
    with pytest.raises(HTTPException) as exc_info:
        business_objects_service.validate_record_payload(field_defs, {"slot": "midnight"})
    assert exc_info.value.status_code == 422


# ---------------------------------------------------------------------------
# service.create_record / update_record / delete_record (no SELECT needed)
# ---------------------------------------------------------------------------


async def test_create_record_validates_then_adds_to_session() -> None:
    session = _FakeSession()
    object_type = _object_type()
    field_defs = [_field("address", FieldType.TEXT, required=True)]
    run_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    record = await business_objects_service.create_record(
        session,
        tenant_id=_TENANT_ID,
        object_type=object_type,
        field_defs=field_defs,
        payload={"address": "12 Main St"},
        customer_id=customer_id,
        created_by_run_id=run_id,
    )

    assert record in session.added
    assert record.tenant_id == _TENANT_ID
    assert record.object_type_id == object_type.id
    assert record.payload == {"address": "12 Main St"}
    assert record.customer_id == customer_id
    assert record.created_by_run_id == run_id


async def test_create_record_rejects_invalid_payload_before_touching_session() -> None:
    session = _FakeSession()
    field_defs = [_field("address", FieldType.TEXT, required=True)]

    with pytest.raises(HTTPException):
        await business_objects_service.create_record(
            session, tenant_id=_TENANT_ID, object_type=_object_type(), field_defs=field_defs, payload={}
        )

    assert session.added == []


async def test_update_record_merges_payload_and_revalidates() -> None:
    session = _FakeSession()
    field_defs = [_field("address", FieldType.TEXT, required=True), _field("notes", FieldType.TEXT)]
    record = ObjectRecord(
        id=uuid.uuid4(),
        tenant_id=_TENANT_ID,
        object_type_id=uuid.uuid4(),
        payload={"address": "12 Main St"},
    )

    updated = await business_objects_service.update_record(
        session, record, field_defs=field_defs, payload={"notes": "leave at the gate"}
    )

    assert updated.payload == {"address": "12 Main St", "notes": "leave at the gate"}


async def test_delete_record_removes_from_session() -> None:
    class _DeletingFakeSession(_FakeSession):
        def __init__(self) -> None:
            super().__init__()
            self.deleted: list[Any] = []

        async def delete(self, obj: Any) -> None:
            self.deleted.append(obj)

    session = _DeletingFakeSession()
    record = ObjectRecord(id=uuid.uuid4(), tenant_id=_TENANT_ID, object_type_id=uuid.uuid4(), payload={})

    await business_objects_service.delete_record(session, record)

    assert record in session.deleted


# ---------------------------------------------------------------------------
# workflow_adapter.resolve / CustomObjectQueryAdapter
# ---------------------------------------------------------------------------


async def test_resolve_returns_none_when_no_matching_type(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_lookup(session, *, tenant_id, key):
        return None

    monkeypatch.setattr(business_objects_workflow_adapter.business_objects_service, "get_object_type_by_key", fake_lookup)

    adapter = await business_objects_workflow_adapter.resolve(None, tenant_id=_TENANT_ID, key="delivery")
    assert adapter is None


async def test_resolve_returns_none_for_inactive_type(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_lookup(session, *, tenant_id, key):
        return _object_type(key=key, is_active=False)

    monkeypatch.setattr(business_objects_workflow_adapter.business_objects_service, "get_object_type_by_key", fake_lookup)

    adapter = await business_objects_workflow_adapter.resolve(None, tenant_id=_TENANT_ID, key="delivery")
    assert adapter is None


async def test_resolve_returns_adapter_bound_to_the_type(monkeypatch: pytest.MonkeyPatch) -> None:
    object_type = _object_type(key="delivery")

    async def fake_lookup(session, *, tenant_id, key):
        assert key == "delivery"
        return object_type

    monkeypatch.setattr(business_objects_workflow_adapter.business_objects_service, "get_object_type_by_key", fake_lookup)

    adapter = await business_objects_workflow_adapter.resolve(None, tenant_id=_TENANT_ID, key="delivery")
    assert adapter is not None
    assert adapter.module_key == "delivery"
    assert adapter.object_type is object_type


async def test_custom_object_adapter_create_translates_http_exception_to_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    object_type = _object_type()
    adapter = business_objects_workflow_adapter.CustomObjectQueryAdapter(object_type)

    async def fake_list_field_definitions(session, *, tenant_id, object_type_id):
        return []

    async def fake_create_record(session, **kwargs):
        raise HTTPException(status_code=422, detail={"message": "record payload validation failed", "errors": []})

    monkeypatch.setattr(
        business_objects_workflow_adapter.business_objects_service,
        "list_field_definitions",
        fake_list_field_definitions,
    )
    monkeypatch.setattr(business_objects_workflow_adapter.business_objects_service, "create_record", fake_create_record)

    with pytest.raises(ValueError, match="record payload validation failed"):
        await adapter.create(None, tenant_id=_TENANT_ID, fields={})


# ---------------------------------------------------------------------------
# module.list / module.get / module.create / module.update: runtime
# fallback to a tenant-defined custom object type
# ---------------------------------------------------------------------------


def _context(config: dict[str, Any], *, session: Any = "not-none") -> ExecutionContext:
    return ExecutionContext(
        session=session,
        tenant_id=_TENANT_ID,
        run_id=uuid.uuid4(),
        node_id="node-under-test",
        config=config,
        variables={},
    )


class _FakeCustomAdapter:
    module_key = "delivery"

    def __init__(self) -> None:
        self.captured: dict[str, Any] = {}

    async def list(self, session, *, tenant_id, filters, limit):
        self.captured["list"] = {"filters": filters, "limit": limit}
        return [{"id": "1", "address": "12 Main St"}]

    async def get(self, session, *, tenant_id, item_id):
        self.captured["get"] = {"item_id": item_id}
        return {"id": str(item_id), "address": "12 Main St"}

    async def create(self, session, *, tenant_id, fields):
        self.captured["create"] = {"fields": fields}
        return {"id": "new-id", **fields}

    async def update(self, session, *, tenant_id, item_id, fields):
        self.captured["update"] = {"item_id": item_id, "fields": fields}
        return {"id": str(item_id), **fields}


async def test_module_list_falls_back_to_custom_object_when_registry_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    fake_adapter = _FakeCustomAdapter()

    async def fake_resolve(session, *, tenant_id, key):
        assert key == "delivery"
        return fake_adapter

    monkeypatch.setattr(business_objects_workflow_adapter, "resolve", fake_resolve)

    result = await module_list_node.ModuleListExecutor().execute(_context({"module": "delivery"}))

    assert isinstance(result, Success)
    assert result.output["items"] == [{"id": "1", "address": "12 Main St"}]


async def test_module_get_falls_back_to_custom_object_when_registry_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    fake_adapter = _FakeCustomAdapter()

    async def fake_resolve(session, *, tenant_id, key):
        return fake_adapter

    monkeypatch.setattr(business_objects_workflow_adapter, "resolve", fake_resolve)

    item_id = uuid.uuid4()
    result = await module_get_node.ModuleGetExecutor().execute(_context({"module": "delivery", "item_id": str(item_id)}))

    assert isinstance(result, Success)
    assert result.output["item"]["id"] == str(item_id)


async def test_module_create_falls_back_to_custom_object_when_registry_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    fake_adapter = _FakeCustomAdapter()

    async def fake_resolve(session, *, tenant_id, key):
        return fake_adapter

    monkeypatch.setattr(business_objects_workflow_adapter, "resolve", fake_resolve)

    result = await module_create_node.ModuleCreateExecutor().execute(
        _context({"module": "delivery", "fields": {"address": "12 Main St"}})
    )

    assert isinstance(result, Success)
    assert result.output == {"item": {"id": "new-id", "address": "12 Main St"}}


async def test_module_create_translates_custom_object_value_error_to_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)

    class _RejectingAdapter(_FakeCustomAdapter):
        async def create(self, session, *, tenant_id, fields):
            raise ValueError("record payload validation failed")

    async def fake_resolve(session, *, tenant_id, key):
        return _RejectingAdapter()

    monkeypatch.setattr(business_objects_workflow_adapter, "resolve", fake_resolve)

    result = await module_create_node.ModuleCreateExecutor().execute(
        _context({"module": "delivery", "fields": {}})
    )

    assert isinstance(result, Failure)
    assert "record payload validation failed" in result.error


async def test_module_update_falls_back_to_custom_object_when_registry_misses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    fake_adapter = _FakeCustomAdapter()

    async def fake_resolve(session, *, tenant_id, key):
        return fake_adapter

    monkeypatch.setattr(business_objects_workflow_adapter, "resolve", fake_resolve)

    item_id = uuid.uuid4()
    result = await module_update_node.ModuleUpdateExecutor().execute(
        _context({"module": "delivery", "item_id": str(item_id), "fields": {"address": "new address"}})
    )

    assert isinstance(result, Success)
    assert result.output["item"]["address"] == "new address"


async def test_module_list_still_fails_cleanly_when_both_registry_and_custom_object_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)

    async def fake_resolve(session, *, tenant_id, key):
        return None

    monkeypatch.setattr(business_objects_workflow_adapter, "resolve", fake_resolve)

    result = await module_list_node.ModuleListExecutor().execute(_context({"module": "bogus"}))

    assert isinstance(result, Failure)
    assert "bogus" in result.error


async def test_module_list_skips_custom_object_fallback_when_session_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard for the pre-existing (session=None) unit tests in
    test_workflow_module_nodes.py: they must keep failing cleanly without
    this fallback ever touching a (nonexistent) database."""
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    called = False

    async def fake_resolve(session, *, tenant_id, key):
        nonlocal called
        called = True
        return None

    monkeypatch.setattr(business_objects_workflow_adapter, "resolve", fake_resolve)

    result = await module_list_node.ModuleListExecutor().execute(_context({"module": "bogus"}, session=None))

    assert isinstance(result, Failure)
    assert called is False


# ---------------------------------------------------------------------------
# requires_postgres: real round-trips + tenant isolation
#
# Two real `businesses` rows are required (FK from object_type_definitions/
# object_records to businesses.id) - same fixture shape as
# test_rls_isolation.py's `tenants` fixture, cleaned up afterward.
# ---------------------------------------------------------------------------


@pytest.fixture
async def two_businesses(pg_session_factory):
    from sqlalchemy import text

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    async with pg_session_factory() as session:
        for tenant_id, name in ((tenant_a, "BizObj Tenant A"), (tenant_b, "BizObj Tenant B")):
            await session.execute(
                text("INSERT INTO businesses (id, name, slug, status) VALUES (:id, :name, :slug, 'active')"),
                {"id": tenant_id, "name": name, "slug": f"bizobj-{tenant_id.hex[:12]}"},
            )
        await session.commit()

    yield tenant_a, tenant_b

    async with pg_session_factory() as session:
        await session.execute(text("DELETE FROM businesses WHERE id = ANY(:ids)"), {"ids": [tenant_a, tenant_b]})
        await session.commit()


@requires_postgres
async def test_object_type_and_record_crud_roundtrip(pg_session_factory, two_businesses) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.business_objects.schemas import (
        ObjectFieldDefinitionCreate,
        ObjectRecordUpdate,
        ObjectTypeCreate,
    )

    tenant_id, _ = two_businesses
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_id)

        object_type = await business_objects_service.create_object_type(
            session, tenant_id=tenant_id, payload=ObjectTypeCreate(key="delivery", name="Delivery")
        )
        field_def = await business_objects_service.create_field_definition(
            session,
            tenant_id=tenant_id,
            object_type_id=object_type.id,
            payload=ObjectFieldDefinitionCreate(
                key="address", label="Address", field_type=FieldType.TEXT, required=True
            ),
        )
        record = await business_objects_service.create_record(
            session,
            tenant_id=tenant_id,
            object_type=object_type,
            field_defs=[field_def],
            payload={"address": "12 Main St"},
        )
        await session.commit()

        await set_tenant_context(session, tenant_id)
        fetched = await business_objects_service.get_object_type_by_key(session, tenant_id=tenant_id, key="delivery")
        assert fetched is not None
        assert fetched.id == object_type.id

        updated = await business_objects_service.update_record(
            session,
            record,
            field_defs=[field_def],
            payload=ObjectRecordUpdate(payload={"address": "99 Side St"}).payload,
        )
        await session.commit()
        assert updated.payload["address"] == "99 Side St"


@requires_postgres
async def test_object_types_are_isolated_per_tenant(pg_session_factory, two_businesses) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.business_objects.schemas import ObjectTypeCreate

    tenant_a, tenant_b = two_businesses

    async with pg_session_factory() as session_a:
        await set_tenant_context(session_a, tenant_a)
        await business_objects_service.create_object_type(
            session_a, tenant_id=tenant_a, payload=ObjectTypeCreate(key="delivery", name="Delivery A")
        )
        await session_a.commit()

    async with pg_session_factory() as session_b:
        await set_tenant_context(session_b, tenant_b)
        # Same key, different tenant - must not collide.
        type_b = await business_objects_service.create_object_type(
            session_b, tenant_id=tenant_b, payload=ObjectTypeCreate(key="delivery", name="Delivery B")
        )
        await session_b.commit()

        await set_tenant_context(session_b, tenant_b)
        types_visible_to_b = await business_objects_service.list_object_types(session_b, tenant_id=tenant_b)
        assert [t.id for t in types_visible_to_b] == [type_b.id]

        # Tenant B can never see/get tenant A's row via RLS, even when the
        # application-level filter is (wrongly) passed tenant_a explicitly.
        cross_tenant_lookup = await business_objects_service.get_object_type_by_key(
            session_b, tenant_id=tenant_a, key="delivery"
        )
        assert cross_tenant_lookup is None
