"""Offline unit tests for Phase 6's four generic module-CRUD node
executors (`module.list`/`module.get`/`module.create`/`module.update`) and
the `ModuleQueryAdapter`/`ModuleQueryRegistry` they dispatch through.

Same "no Postgres required" philosophy as `test_workflow_generic_nodes.py`:
the shared `engine.module_registry.registry` singleton's `get_or_none` is
monkeypatched to return a small fake adapter, so these tests never touch a
real module's `service.py` or a real database. All four node executors
dispatch through this one singleton via the shared `resolve_adapter` helper
(`engine/module_registry.py`) - patching the singleton directly, rather than
a per-node-module alias, means the patch takes effect regardless of which
node file's `execute()` ends up calling it.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from fusionflow.modules.workflows.engine import module_registry
from fusionflow.modules.workflows.engine.module_registry import MAX_LIST_LIMIT
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.nodes import module_create as module_create_node
from fusionflow.modules.workflows.nodes import module_get as module_get_node
from fusionflow.modules.workflows.nodes import module_list as module_list_node
from fusionflow.modules.workflows.nodes import module_update as module_update_node

pytestmark = pytest.mark.asyncio


def _context(config: dict[str, Any], variables: dict[str, Any] | None = None) -> ExecutionContext:
    return ExecutionContext(
        session=None,
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="node-under-test",
        config=config,
        variables=variables or {},
    )


class _FakeAdapter:
    """Minimal `ModuleQueryAdapter`-shaped stand-in. `create`/`update`
    default to the base class's `NotImplementedError` behavior unless a
    subclass overrides them - mirrors `orders`/`payments`'s real exceptions."""

    module_key = "fake"

    def __init__(self, *, items: list[dict[str, Any]] | None = None, item: dict[str, Any] | None = None) -> None:
        self.items = items or []
        self.item = item
        self.captured: dict[str, Any] = {}

    async def list(self, session: Any, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int) -> list[dict]:
        self.captured["list"] = {"filters": filters, "limit": limit}
        return self.items

    async def get(self, session: Any, *, tenant_id: uuid.UUID, item_id: uuid.UUID) -> dict | None:
        self.captured["get"] = {"item_id": item_id}
        return self.item

    async def create(self, session: Any, *, tenant_id: uuid.UUID, fields: dict[str, Any]) -> dict:
        raise NotImplementedError("fake module does not support create")

    async def update(
        self, session: Any, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict | None:
        raise NotImplementedError("fake module does not support update")


class _CreatableAdapter(_FakeAdapter):
    async def create(self, session: Any, *, tenant_id: uuid.UUID, fields: dict[str, Any]) -> dict:
        self.captured["create"] = {"fields": fields}
        return {"id": "new-id", **fields}

    async def update(
        self, session: Any, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict | None:
        self.captured["update"] = {"item_id": item_id, "fields": fields}
        if self.item is None:
            return None
        return {**self.item, **fields}


# --------------------------------------------------------------------------
# module.list
# --------------------------------------------------------------------------


async def test_module_list_unknown_module_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    result = await module_list_node.ModuleListExecutor().execute(_context({"module": "bogus"}))
    assert isinstance(result, Failure)
    assert "bogus" in result.error


async def test_module_list_dispatches_and_returns_items(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _FakeAdapter(items=[{"id": "1"}, {"id": "2"}])
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await module_list_node.ModuleListExecutor().execute(
        _context({"module": "products", "filters": {"is_active": True}, "limit": 10})
    )

    assert isinstance(result, Success)
    assert result.output == {"items": [{"id": "1"}, {"id": "2"}], "count": 2}
    assert adapter.captured["list"] == {"filters": {"is_active": True}, "limit": 10}


async def test_module_list_clamps_limit_to_server_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _FakeAdapter()
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    # Config-level validation itself rejects anything over the ceiling...
    with pytest.raises(ValidationError):
        module_list_node.ModuleListConfig.model_validate({"module": "products", "limit": MAX_LIST_LIMIT + 1})

    # ...but even a config-valid limit is defensively re-clamped at dispatch time.
    result = await module_list_node.ModuleListExecutor().execute(
        _context({"module": "products", "limit": MAX_LIST_LIMIT})
    )
    assert isinstance(result, Success)
    assert adapter.captured["list"]["limit"] == MAX_LIST_LIMIT


# --------------------------------------------------------------------------
# module.get
# --------------------------------------------------------------------------


async def test_module_get_unknown_module_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: None)
    result = await module_get_node.ModuleGetExecutor().execute(
        _context({"module": "bogus", "item_id": str(uuid.uuid4())})
    )
    assert isinstance(result, Failure)


async def test_module_get_invalid_uuid_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: _FakeAdapter())
    result = await module_get_node.ModuleGetExecutor().execute(_context({"module": "products", "item_id": "not-a-uuid"}))
    assert isinstance(result, Failure)
    assert "not a valid UUID" in result.error


async def test_module_get_not_found_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _FakeAdapter(item=None)
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)
    result = await module_get_node.ModuleGetExecutor().execute(
        _context({"module": "products", "item_id": str(uuid.uuid4())})
    )
    assert isinstance(result, Failure)
    assert "not found" in result.error


async def test_module_get_success_resolves_templated_id(monkeypatch: pytest.MonkeyPatch) -> None:
    item_id = uuid.uuid4()
    adapter = _FakeAdapter(item={"id": str(item_id), "name": "Widget"})
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await module_get_node.ModuleGetExecutor().execute(
        _context({"module": "products", "item_id": "{{trigger.product_id}}"}, {"trigger": {"product_id": str(item_id)}})
    )

    assert isinstance(result, Success)
    assert result.output == {"item": {"id": str(item_id), "name": "Widget"}}
    assert adapter.captured["get"]["item_id"] == item_id


# --------------------------------------------------------------------------
# module.create
# --------------------------------------------------------------------------


async def test_module_create_not_implemented_is_a_clean_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors the real Payments adapter, which has no `create` override."""
    adapter = _FakeAdapter()
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await module_create_node.ModuleCreateExecutor().execute(
        _context({"module": "payments", "fields": {"amount": "10.00"}})
    )

    assert isinstance(result, Failure)
    assert "does not support create" in result.error


async def test_module_create_success(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _CreatableAdapter()
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await module_create_node.ModuleCreateExecutor().execute(
        _context({"module": "tickets", "fields": {"subject": "Help"}})
    )

    assert isinstance(result, Success)
    assert result.output == {"item": {"id": "new-id", "subject": "Help"}}


async def test_module_create_blocked_at_resource_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _CreatableAdapter()
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    async def fake_get_resource_limit(session: Any, *, tenant_id: uuid.UUID, resource_key: str) -> int | None:
        return 2

    async def fake_count(session: Any, tenant_id: uuid.UUID) -> int:
        return 2

    monkeypatch.setattr(module_create_node.admin_service, "get_resource_limit", fake_get_resource_limit)
    monkeypatch.setattr(module_create_node, "_COUNT_FNS", {"products": fake_count})

    result = await module_create_node.ModuleCreateExecutor().execute(
        _context({"module": "products", "fields": {"name": "Widget"}})
    )

    assert isinstance(result, Failure)
    assert "limit" in result.error
    assert "create" not in adapter.captured


async def test_module_create_under_limit_proceeds(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _CreatableAdapter()
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    async def fake_get_resource_limit(session: Any, *, tenant_id: uuid.UUID, resource_key: str) -> int | None:
        return 5

    async def fake_count(session: Any, tenant_id: uuid.UUID) -> int:
        return 2

    monkeypatch.setattr(module_create_node.admin_service, "get_resource_limit", fake_get_resource_limit)
    monkeypatch.setattr(module_create_node, "_COUNT_FNS", {"products": fake_count})

    result = await module_create_node.ModuleCreateExecutor().execute(
        _context({"module": "products", "fields": {"name": "Widget"}})
    )

    assert isinstance(result, Success)
    assert adapter.captured["create"]["fields"] == {"name": "Widget"}


# --------------------------------------------------------------------------
# module.update
# --------------------------------------------------------------------------


async def test_module_update_not_implemented_is_a_clean_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors the real Payments adapter, which has no `update` override."""
    adapter = _FakeAdapter()
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await module_update_node.ModuleUpdateExecutor().execute(
        _context({"module": "payments", "item_id": str(uuid.uuid4()), "fields": {"status": "succeeded"}})
    )

    assert isinstance(result, Failure)
    assert "does not support update" in result.error


async def test_module_update_orders_rejects_non_status_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mirrors the real Orders adapter's `ValueError` for any field beyond `status`."""

    class _OrdersLikeAdapter(_FakeAdapter):
        async def update(
            self, session: Any, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
        ) -> dict | None:
            extra = set(fields) - {"status"}
            if extra:
                raise ValueError(f"module.update on 'orders' only supports the 'status' field - got {sorted(extra)}")
            return {"id": str(item_id), **fields}

    adapter = _OrdersLikeAdapter()
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await module_update_node.ModuleUpdateExecutor().execute(
        _context({"module": "orders", "item_id": str(uuid.uuid4()), "fields": {"total_amount": "999.00"}})
    )

    assert isinstance(result, Failure)
    assert "only supports the 'status' field" in result.error


async def test_module_update_not_found_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = _CreatableAdapter(item=None)
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await module_update_node.ModuleUpdateExecutor().execute(
        _context({"module": "tickets", "item_id": str(uuid.uuid4()), "fields": {"status": "resolved"}})
    )

    assert isinstance(result, Failure)
    assert "not found" in result.error


async def test_module_update_success(monkeypatch: pytest.MonkeyPatch) -> None:
    item_id = uuid.uuid4()
    adapter = _CreatableAdapter(item={"id": str(item_id), "status": "open"})
    monkeypatch.setattr(module_registry.registry, "get_or_none", lambda key: adapter)

    result = await module_update_node.ModuleUpdateExecutor().execute(
        _context({"module": "tickets", "item_id": str(item_id), "fields": {"status": "resolved"}})
    )

    assert isinstance(result, Success)
    assert result.output == {"item": {"id": str(item_id), "status": "resolved"}}
