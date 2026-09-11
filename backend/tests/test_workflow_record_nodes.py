"""Offline unit tests for `records.query`/`records.upsert` (composable-
builder redesign, Phase 3) - the friendly, module-picker-driven front doors
over `module.list`/`module.get`/`module.create`/`module.update`.

Same "no Postgres required" philosophy as `test_workflow_module_nodes.py`:
the shared `engine.module_registry.registry` singleton is monkeypatched to
return a small fake adapter (covering both a fixed-module-shaped adapter and
a custom-object-shaped one), so these tests never touch a real database.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from fusionflow.modules.workflows.engine import module_registry
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.nodes import record_query as record_query_node
from fusionflow.modules.workflows.nodes import record_upsert as record_upsert_node

pytestmark = pytest.mark.asyncio


def _context(config: dict[str, Any], variables: dict[str, Any] | None = None, *, session: Any = "not-none") -> ExecutionContext:
    return ExecutionContext(
        session=session,
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="node-under-test",
        config=config,
        variables=variables or {},
    )


class _FakeAdapter:
    module_key = "fake"

    def __init__(self, *, items=None, item=None) -> None:
        self.items = items or []
        self.item = item
        self.captured: dict[str, Any] = {}

    async def list(self, session, *, tenant_id, filters, limit):
        self.captured["list"] = {"filters": filters, "limit": limit}
        return self.items

    async def get(self, session, *, tenant_id, item_id):
        self.captured["get"] = {"item_id": item_id}
        return self.item

    async def create(self, session, *, tenant_id, fields):
        self.captured["create"] = {"fields": fields}
        return {"id": "new-id", **fields}

    async def update(self, session, *, tenant_id, item_id, fields):
        self.captured["update"] = {"item_id": item_id, "fields": fields}
        if self.item is None:
            return None
        return {**self.item, **fields}


# --------------------------------------------------------------------------
# records.query
# --------------------------------------------------------------------------


async def test_records_query_unknown_module_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    result = await record_query_node.RecordQueryExecutor().execute(
        _context({"module": "bogus", "operation": "list"}, session=None)
    )
    assert isinstance(result, Failure)
    assert "bogus" in result.error


async def test_records_query_list_dispatches_and_returns_items(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _FakeAdapter(items=[{"id": "1"}, {"id": "2"}])
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await record_query_node.RecordQueryExecutor().execute(
        _context({"module": "products", "operation": "list", "filters": {"is_active": True}, "limit": 10})
    )

    assert isinstance(result, Success)
    assert result.output == {"items": [{"id": "1"}, {"id": "2"}], "count": 2}
    assert adapter.captured["list"] == {"filters": {"is_active": True}, "limit": 10}


async def test_records_query_get_requires_item_id() -> None:
    result = await record_query_node.RecordQueryExecutor().execute(
        _context({"module": "products", "operation": "get"})
    )
    assert isinstance(result, Failure)
    assert "item_id" in result.error


async def test_records_query_get_success_resolves_templated_id(monkeypatch: pytest.MonkeyPatch) -> None:
    item_id = uuid.uuid4()
    adapter = _FakeAdapter(item={"id": str(item_id), "name": "Widget"})
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await record_query_node.RecordQueryExecutor().execute(
        _context(
            {"module": "products", "operation": "get", "item_id": "{{trigger.product_id}}"},
            {"trigger": {"product_id": str(item_id)}},
        )
    )

    assert isinstance(result, Success)
    assert result.output == {"item": {"id": str(item_id), "name": "Widget"}}


async def test_records_query_get_not_found_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _FakeAdapter(item=None)
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await record_query_node.RecordQueryExecutor().execute(
        _context({"module": "products", "operation": "get", "item_id": str(uuid.uuid4())})
    )
    assert isinstance(result, Failure)
    assert "not found" in result.error


async def test_records_query_falls_back_to_custom_object(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard: `records.query` must go through the exact same
    `resolve_adapter` fallback as `module.list`/`module.get` (Phase 2)."""
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    adapter = _FakeAdapter(items=[{"id": "1", "address": "12 Main St"}])

    async def fake_resolve(session, *, tenant_id, key):
        assert key == "delivery"
        return adapter

    monkeypatch.setattr(
        "fusionflow.modules.business_objects.workflow_adapter.resolve", fake_resolve
    )

    result = await record_query_node.RecordQueryExecutor().execute(
        _context({"module": "delivery", "operation": "list"})
    )
    assert isinstance(result, Success)
    assert result.output["items"] == [{"id": "1", "address": "12 Main St"}]


# --------------------------------------------------------------------------
# records.upsert
# --------------------------------------------------------------------------


async def test_records_upsert_unknown_module_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    result = await record_upsert_node.RecordUpsertExecutor().execute(
        _context({"module": "bogus", "operation": "create", "fields": {}}, session=None)
    )
    assert isinstance(result, Failure)
    assert "bogus" in result.error


async def test_records_upsert_create_success(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _FakeAdapter()
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await record_upsert_node.RecordUpsertExecutor().execute(
        _context({"module": "tickets", "operation": "create", "fields": {"subject": "Help"}})
    )

    assert isinstance(result, Success)
    assert result.output == {"item": {"id": "new-id", "subject": "Help"}}


async def test_records_upsert_create_blocked_at_resource_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _FakeAdapter()
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    async def fake_get_resource_limit(session, *, tenant_id, resource_key):
        return 2

    async def fake_count(session, tenant_id) -> int:
        return 2

    monkeypatch.setattr(record_upsert_node.admin_service, "get_resource_limit", fake_get_resource_limit)
    monkeypatch.setattr(record_upsert_node, "_COUNT_FNS", {"products": fake_count})

    result = await record_upsert_node.RecordUpsertExecutor().execute(
        _context({"module": "products", "operation": "create", "fields": {"name": "Widget"}})
    )

    assert isinstance(result, Failure)
    assert "limit" in result.error
    assert "create" not in adapter.captured


async def test_records_upsert_update_requires_item_id() -> None:
    result = await record_upsert_node.RecordUpsertExecutor().execute(
        _context({"module": "tickets", "operation": "update", "fields": {"status": "resolved"}})
    )
    assert isinstance(result, Failure)
    assert "item_id" in result.error


async def test_records_upsert_update_success(monkeypatch: pytest.MonkeyPatch) -> None:
    item_id = uuid.uuid4()
    adapter = _FakeAdapter(item={"id": str(item_id), "status": "open"})
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await record_upsert_node.RecordUpsertExecutor().execute(
        _context({"module": "tickets", "operation": "update", "item_id": str(item_id), "fields": {"status": "resolved"}})
    )

    assert isinstance(result, Success)
    assert result.output == {"item": {"id": str(item_id), "status": "resolved"}}


async def test_records_upsert_update_not_found_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _FakeAdapter(item=None)
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await record_upsert_node.RecordUpsertExecutor().execute(
        _context({"module": "tickets", "operation": "update", "item_id": str(uuid.uuid4()), "fields": {}})
    )
    assert isinstance(result, Failure)
    assert "not found" in result.error


async def test_records_upsert_falls_back_to_custom_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    adapter = _FakeAdapter()

    async def fake_resolve(session, *, tenant_id, key):
        assert key == "delivery"
        return adapter

    monkeypatch.setattr(
        "fusionflow.modules.business_objects.workflow_adapter.resolve", fake_resolve
    )

    result = await record_upsert_node.RecordUpsertExecutor().execute(
        _context({"module": "delivery", "operation": "create", "fields": {"address": "12 Main St"}})
    )
    assert isinstance(result, Success)
    assert result.output == {"item": {"id": "new-id", "address": "12 Main St"}}
