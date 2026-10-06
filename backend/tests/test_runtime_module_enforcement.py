"""Offline tests for runtime module-entitlement enforcement (admin revoke
after publish) and the admin revoke-impact endpoint's service function.

No Postgres: `entitlement.key_access` / the connector service are
monkeypatched, sessions are minimal fakes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.workflows import validation
from fusionflow.modules.workflows.engine import entitlement
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.run_loop import execute_run
from fusionflow.modules.workflows.models import RunStatus, StepStatus, WorkflowRun

pytestmark = pytest.mark.asyncio  # noqa


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def get(self, model: Any, ident: Any) -> Any:
        return None


def _run() -> WorkflowRun:
    return WorkflowRun(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        trigger_event_ref="test",
        status=RunStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
        loop_guard_count=0,
    )


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {"id": node_id, "type": node_type, "data": {"nodeType": node_type, "config": config or {}}}


def _graph_with_module_node() -> WorkflowGraph:
    return WorkflowGraph.from_json(
        {
            "nodes": [
                _node("t", "manual.test_trigger"),
                _node("m", "module.list", {"module": "orders"}),
                _node("after", "log.noop"),
            ],
            "edges": [
                {"id": "e1", "source": "t", "target": "m"},
                {"id": "e2", "source": "m", "target": "after"},
            ],
        }
    )


def _patch_access(monkeypatch: pytest.MonkeyPatch, statuses: dict[str, str]) -> list[str]:
    calls: list[str] = []

    async def fake_key_access(session, *, tenant_id, key, cache=None):
        if cache is not None and key in cache:
            return cache[key]
        calls.append(key)
        result = (statuses.get(key, "granted"), key.title())
        if cache is not None:
            cache[key] = result
        return result

    monkeypatch.setattr(entitlement, "key_access", fake_key_access)
    return calls


async def test_node_required_keys_covers_module_and_source_config() -> None:
    graph = _graph_with_module_node()
    assert entitlement.graph_required_keys(graph) == {"orders"}

    ask = WorkflowGraph.from_json(
        {"nodes": [_node("a", "log.noop", {"source": {"kind": "module", "module": "products"}})], "edges": []}
    )
    assert entitlement.graph_required_keys(ask) == {"products"}


async def test_run_fails_terminally_when_module_revoked(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_access(monkeypatch, {"orders": "denied"})
    session, run = FakeSession(), _run()

    result = await execute_run(session, run, _graph_with_module_node())

    assert result.status == RunStatus.FAILED
    steps = {s.node_id: s for s in session.added}
    assert steps["t"].status == StepStatus.SUCCEEDED
    assert steps["m"].status == StepStatus.FAILED
    assert "Module 'orders' was revoked for this business by an administrator" in steps["m"].error
    assert "after" not in steps  # never executed
    assert steps["m"].attempt == 1  # not retried


async def test_run_completes_when_granted_and_caches_lookups(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _patch_access(monkeypatch, {"orders": "granted"})

    async def fake_resolve(session, *, tenant_id, module_key):
        class _A:
            async def list(self, session, *, tenant_id, filters, limit):
                return []

        return _A()

    from fusionflow.modules.workflows.nodes import module_list

    monkeypatch.setattr(module_list, "resolve_adapter", fake_resolve)
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("t", "manual.test_trigger"),
                _node("m1", "module.list", {"module": "orders"}),
                _node("m2", "module.list", {"module": "orders"}),
            ],
            "edges": [
                {"id": "e1", "source": "t", "target": "m1"},
                {"id": "e2", "source": "m1", "target": "m2"},
            ],
        }
    )
    result = await execute_run(FakeSession(), _run(), graph)
    assert result.status == RunStatus.COMPLETED
    assert calls == ["orders"]  # one lookup for two nodes


async def test_publish_validation_flags_non_entitled_module(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_access(monkeypatch, {"orders": "not_requested"})
    result = await validation.validate_for_publish(
        FakeSession(), tenant_id=uuid.uuid4(), graph=_graph_with_module_node()
    )
    issues = [i for i in result.issues if i.rule == "module_not_entitled"]
    assert len(issues) == 1
    assert issues[0].severity == "error" and issues[0].node_id == "m"
    assert "Orders" in issues[0].message


async def test_tenant_has_access_reports_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_access(monkeypatch, {"instagram": "denied"})
    assert not await entitlement.tenant_has_access(
        FakeSession(), tenant_id=uuid.uuid4(), keys=("instagram", "customers")
    )
    assert await entitlement.tenant_has_access(FakeSession(), tenant_id=uuid.uuid4(), keys=("customers",))


# --- revoke-impact ----------------------------------------------------------


class _QueueSession:
    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)

    async def execute(self, *_a: Any, **_k: Any) -> Any:
        value = self._results.pop(0)

        class _R:
            def all(self_inner):
                return value

            def scalars(self_inner):
                return SimpleNamespace(all=lambda: value)

            def scalar_one(self_inner):
                return value

        return _R()


async def test_revoke_impact_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant = uuid.uuid4()
    customers = SimpleNamespace(
        id=uuid.uuid4(), key="customers", display_name="Customers", category=SimpleNamespace(value="feature")
    )
    orders = SimpleNamespace(
        id=uuid.uuid4(), key="orders", display_name="Orders", category=SimpleNamespace(value="feature")
    )

    async def _noop(*a, **k):
        return None

    async def by_key(session, key):
        return customers if key == "customers" else None

    async def list_types(session):
        return [customers, orders]

    async def resolve_map(session, *, tenant_id, connector_types, role=None):
        return {t.id: "granted" for t in connector_types}

    monkeypatch.setattr(admin_service, "set_tenant_context", _noop)
    monkeypatch.setattr(admin_service, "_CONNECTORS_AVAILABLE", True)
    monkeypatch.setattr(admin_service.connector_service, "get_connector_type_by_key", by_key)
    monkeypatch.setattr(admin_service.connector_service, "list_connector_types", list_types)
    monkeypatch.setattr(admin_service.connector_service, "resolve_module_access_map", resolve_map, raising=False)

    wf = SimpleNamespace(id=uuid.uuid4(), name="Order flow")
    version = SimpleNamespace(
        compiled_graph={"nodes": [_node("m", "module.list", {"module": "customers"})], "edges": []}, graph={}
    )
    other = SimpleNamespace(id=uuid.uuid4(), name="Unrelated")
    other_version = SimpleNamespace(compiled_graph={"nodes": [_node("l", "log.noop")], "edges": []}, graph={})
    # queries: workflows, (feature => no instance count), restriction roles, membership count
    session = _QueueSession([[(wf, version), (other, other_version)], ["member"], 4])

    data = await admin_service.get_connector_revoke_impact(session, tenant, "customers")

    assert data["type_key"] == "customers"
    assert {d["key"] for d in data["dependents"]} >= {"orders"}
    assert data["published_workflows"] == [{"id": wf.id, "name": "Order flow"}]
    assert data["connected_instances"] == 0
    assert data["role_restrictions"] == [{"role": "member"}]
    assert data["active_users_count"] == 4
