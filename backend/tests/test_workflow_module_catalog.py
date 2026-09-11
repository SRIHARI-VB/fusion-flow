"""Tests for the unified module-picker catalog (composable-workflow-builder
redesign, Phase 3): `module_catalog.list_modules` merging the 9 fixed
modules with a tenant's own custom object types, and the pure-function
helpers it's built from.

Same "no Postgres required" split as `test_workflow_business_objects.py`:
`supported_operations`/`_schema_to_fields`/`_field_def_to_dict` are pure
(no session), so they're tested directly; `list_modules` itself does no SQL
of its own (it only calls other modules' service functions), so its merge
behavior is exercised by monkeypatching those service calls with small
in-memory fakes - a real Postgres round-trip (confirming those service
calls stay tenant-isolated) is already covered by
`test_workflow_business_objects.py`'s `requires_postgres` tests. One
`requires_postgres` test here confirms the full merge end-to-end.
"""

from __future__ import annotations

import uuid

import pytest

from fusionflow.modules.business_objects import service as business_objects_service
from fusionflow.modules.business_objects.models import ObjectFieldDefinition, ObjectTypeDefinition
from fusionflow.modules.custom_fields import service as custom_fields_service
from fusionflow.modules.custom_fields.models import EntityType, FieldDefinition, FieldType
from fusionflow.modules.workflows import module_catalog

from tests.conftest import requires_postgres

_TENANT_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# supported_operations
# ---------------------------------------------------------------------------


def test_supported_operations_full_crud_modules() -> None:
    for key in ("products", "services", "coupons", "offers", "customers", "tickets", "kb"):
        assert module_catalog.supported_operations(key) == ["list", "get", "create", "update"]


def test_supported_operations_orders_has_no_create() -> None:
    assert module_catalog.supported_operations("orders") == ["list", "get", "update"]


def test_supported_operations_payments_is_list_get_only() -> None:
    assert module_catalog.supported_operations("payments") == ["list", "get"]


def test_supported_operations_unknown_module_is_empty() -> None:
    assert module_catalog.supported_operations("bogus") == []


# ---------------------------------------------------------------------------
# _schema_to_fields / _field_def_to_dict
# ---------------------------------------------------------------------------


def test_schema_to_fields_maps_products_create_schema() -> None:
    spec = module_catalog.FIXED_MODULE_CATALOG["products"]
    fields = module_catalog._schema_to_fields(spec.create_schema, exclude=spec.create_schema_exclude)
    by_key = {f["key"]: f for f in fields}

    assert "custom_fields" not in by_key
    assert "entity_type" not in by_key
    assert by_key["name"]["field_type"] == "text"
    assert by_key["name"]["required"] is True
    assert by_key["base_price"]["field_type"] == "number"
    assert by_key["base_price"]["required"] is False
    assert by_key["is_active"]["field_type"] == "boolean"


def test_schema_to_fields_maps_enum_to_select() -> None:
    spec = module_catalog.FIXED_MODULE_CATALOG["coupons"]
    fields = module_catalog._schema_to_fields(spec.create_schema, exclude=spec.create_schema_exclude)
    by_key = {f["key"]: f for f in fields}
    assert by_key["discount_type"]["field_type"] == "select"
    assert by_key["discount_type"]["options"]


def test_schema_to_fields_none_schema_is_empty() -> None:
    assert module_catalog._schema_to_fields(None, exclude=frozenset()) == []


def test_field_def_to_dict_handles_enum_field_type() -> None:
    field_def = FieldDefinition(
        id=uuid.uuid4(),
        tenant_id=_TENANT_ID,
        entity_type=EntityType.PRODUCT,
        key="warranty_months",
        label="Warranty (months)",
        field_type=FieldType.NUMBER,
        required=False,
        sort_order=0,
    )
    result = module_catalog._field_def_to_dict(field_def)
    assert result == {
        "key": "warranty_months",
        "label": "Warranty (months)",
        "field_type": "number",
        "options": None,
        "required": False,
    }


# ---------------------------------------------------------------------------
# list_modules: merge behavior (offline, service calls monkeypatched)
# ---------------------------------------------------------------------------


async def test_list_modules_merges_fixed_and_custom(monkeypatch: pytest.MonkeyPatch) -> None:
    extra_field = FieldDefinition(
        id=uuid.uuid4(),
        tenant_id=_TENANT_ID,
        entity_type=EntityType.PRODUCT,
        key="warranty_months",
        label="Warranty (months)",
        field_type=FieldType.NUMBER,
        required=False,
        sort_order=0,
    )

    async def fake_list_field_definitions(session, *, tenant_id, entity_type):
        return [extra_field] if entity_type == EntityType.PRODUCT else []

    monkeypatch.setattr(custom_fields_service, "list_field_definitions", fake_list_field_definitions)

    delivery_type = ObjectTypeDefinition(
        id=uuid.uuid4(), tenant_id=_TENANT_ID, key="delivery", name="Delivery", icon="truck", is_active=True
    )
    delivery_field = ObjectFieldDefinition(
        id=uuid.uuid4(),
        tenant_id=_TENANT_ID,
        object_type_id=delivery_type.id,
        key="address",
        label="Address",
        field_type=FieldType.TEXT,
        required=True,
        sort_order=0,
    )

    async def fake_list_object_types(session, *, tenant_id, is_active=None):
        return [delivery_type]

    async def fake_list_object_field_definitions(session, *, tenant_id, object_type_id):
        return [delivery_field] if object_type_id == delivery_type.id else []

    monkeypatch.setattr(business_objects_service, "list_object_types", fake_list_object_types)
    monkeypatch.setattr(business_objects_service, "list_field_definitions", fake_list_object_field_definitions)

    entries = await module_catalog.list_modules(None, tenant_id=_TENANT_ID)
    by_key = {e.key: e for e in entries}

    assert set(module_catalog.FIXED_MODULE_CATALOG) <= set(by_key)
    assert by_key["delivery"].source == "custom"
    assert by_key["delivery"].supported_operations == ["list", "get", "create", "update"]
    assert by_key["delivery"].fields == [
        {"key": "address", "label": "Address", "field_type": "text", "options": None, "required": True}
    ]

    products_field_keys = {f["key"] for f in by_key["products"].fields}
    assert "warranty_months" in products_field_keys
    assert by_key["products"].source == "fixed"

    assert by_key["orders"].supported_operations == ["list", "get", "update"]
    assert by_key["payments"].supported_operations == ["list", "get"]


# ---------------------------------------------------------------------------
# requires_postgres: full end-to-end merge, real tenant isolation
# ---------------------------------------------------------------------------


@pytest.fixture
async def one_business(pg_session_factory):
    from sqlalchemy import text

    tenant_id = uuid.uuid4()
    async with pg_session_factory() as session:
        await session.execute(
            text("INSERT INTO businesses (id, name, slug, status) VALUES (:id, :name, :slug, 'active')"),
            {"id": tenant_id, "name": "Module Catalog Tenant", "slug": f"modcat-{tenant_id.hex[:12]}"},
        )
        await session.commit()

    yield tenant_id

    async with pg_session_factory() as session:
        await session.execute(text("DELETE FROM businesses WHERE id = :id"), {"id": tenant_id})
        await session.commit()


@requires_postgres
async def test_list_modules_end_to_end_with_a_real_custom_object_type(pg_session_factory, one_business) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.business_objects.schemas import ObjectFieldDefinitionCreate, ObjectTypeCreate

    tenant_id = one_business
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_id)
        object_type = await business_objects_service.create_object_type(
            session, tenant_id=tenant_id, payload=ObjectTypeCreate(key="appointment", name="Appointment")
        )
        await business_objects_service.create_field_definition(
            session,
            tenant_id=tenant_id,
            object_type_id=object_type.id,
            payload=ObjectFieldDefinitionCreate(
                key="slot", label="Time Slot", field_type=FieldType.TEXT, required=True
            ),
        )
        await session.commit()

        await set_tenant_context(session, tenant_id)
        entries = await module_catalog.list_modules(session, tenant_id=tenant_id)

    by_key = {e.key: e for e in entries}
    assert by_key["appointment"].source == "custom"
    assert by_key["appointment"].fields[0]["key"] == "slot"
    assert set(module_catalog.FIXED_MODULE_CATALOG) <= set(by_key)
