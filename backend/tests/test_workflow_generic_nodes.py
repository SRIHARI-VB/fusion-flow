"""Offline unit tests for Part D's generic, highly-parameterized node
executors (`connector.action`, `http.request`, `condition.multi_branch`,
`data.transform`) — the "catalog/config, not code" extensibility layer.

Same "no Postgres required" philosophy as `test_workflow_connector_nodes.py`:
DB-touching dependencies (`connector_service.get_instance`, the connector
registry) are monkeypatched; `http.request`'s network call is faked via a
monkeypatched `httpx.AsyncClient.request` rather than a real socket.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState, ConnectorType
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.nodes import condition_multi_branch as multi_branch_node
from fusionflow.modules.workflows.nodes import connector_action as connector_action_node
from fusionflow.modules.workflows.nodes import data_transform as data_transform_node
from fusionflow.modules.workflows.nodes import http_request as http_request_node

pytestmark = pytest.mark.asyncio


def _context(config: dict[str, Any], variables: dict[str, Any], session: Any = None) -> ExecutionContext:
    return ExecutionContext(
        session=session,
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="node-under-test",
        config=config,
        variables=variables,
    )


# --------------------------------------------------------------------------
# connector.action
# --------------------------------------------------------------------------


def _fake_instance(tenant_id: uuid.UUID, type_key: str = "whatsapp") -> ConnectorInstance:
    instance = ConnectorInstance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_type_id=uuid.uuid4(),
        state=ConnectorState.CONNECTED,
        display_name="Test",
    )
    instance.connector_type = ConnectorType(id=instance.connector_type_id, key=type_key, display_name=type_key)
    return instance


async def test_connector_action_dispatches_to_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    captured: dict[str, Any] = {}

    class _FakeAdapter:
        async def perform_action(self, *, action: str, params: dict[str, Any], instance: Any, session: Any) -> dict:
            captured["action"] = action
            captured["params"] = params
            return {"sent": True}

    monkeypatch.setattr(connector_action_node.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(connector_action_node.connector_registry, "get_or_none", lambda key: _FakeAdapter())

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="node",
        config={
            "connector_instance_id": str(instance.id),
            "action": "send_text_message",
            "params": {"to": "{{trigger.from}}", "body": "static"},
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await connector_action_node.ConnectorActionExecutor().execute(context)

    assert isinstance(result, Success)
    assert result.output == {"sent": True}
    assert captured["action"] == "send_text_message"
    assert captured["params"] == {"to": "15551234567", "body": "static"}


async def test_connector_action_missing_instance_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(connector_action_node.connector_service, "get_instance", fake_get_instance)

    context = _context({"connector_instance_id": str(uuid.uuid4()), "action": "x"}, {})
    result = await connector_action_node.ConnectorActionExecutor().execute(context)

    assert isinstance(result, Failure)
    assert "not found" in result.error


async def test_connector_action_unknown_action_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    class _FakeAdapter:
        async def perform_action(self, **kwargs: Any) -> dict:
            raise NotImplementedError("whatsapp does not support action 'bogus'")

    monkeypatch.setattr(connector_action_node.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(connector_action_node.connector_registry, "get_or_none", lambda key: _FakeAdapter())

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="node",
        config={"connector_instance_id": str(instance.id), "action": "bogus"},
        variables={},
    )
    result = await connector_action_node.ConnectorActionExecutor().execute(context)

    assert isinstance(result, Failure)
    assert "bogus" in result.error


# --------------------------------------------------------------------------
# http.request
# --------------------------------------------------------------------------


class _FakeHttpResponse:
    def __init__(self, status_code: int, json_body: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_body = json_body
        self.text = text if json_body is None else ""

    def json(self) -> Any:
        if self._json_body is None:
            raise ValueError("no json body")
        return self._json_body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


async def test_http_request_interpolates_and_returns_parsed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_request(self: Any, method: str, url: str, *, headers: dict, json: Any, content: Any) -> Any:
        captured.update(method=method, url=url, headers=headers, json=json)
        return _FakeHttpResponse(200, json_body={"ok": True})

    monkeypatch.setattr(http_request_node.httpx.AsyncClient, "request", fake_request)

    context = _context(
        {
            "method": "POST",
            "url": "https://example.com/orders/{{trigger.id}}",
            "headers": {"X-Token": "{{trigger.token}}"},
            "body": {"note": "{{trigger.note}}"},
        },
        {"trigger": {"id": "42", "token": "secret", "note": "hi"}},
    )

    result = await http_request_node.HttpRequestExecutor().execute(context)

    assert isinstance(result, Success)
    assert result.output == {"status_code": 200, "body": {"ok": True}}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://example.com/orders/42"
    assert captured["headers"] == {"X-Token": "secret"}
    assert captured["json"] == {"note": "hi"}


async def test_http_request_4xx_is_a_failure_not_an_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(self: Any, method: str, url: str, *, headers: dict, json: Any, content: Any) -> Any:
        return _FakeHttpResponse(404, text="not found")

    monkeypatch.setattr(http_request_node.httpx.AsyncClient, "request", fake_request)

    context = _context({"url": "https://example.com/missing"}, {})
    result = await http_request_node.HttpRequestExecutor().execute(context)

    assert isinstance(result, Failure)
    assert "404" in result.error


async def test_http_request_5xx_raises_for_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_request(self: Any, method: str, url: str, *, headers: dict, json: Any, content: Any) -> Any:
        return _FakeHttpResponse(503)

    monkeypatch.setattr(http_request_node.httpx.AsyncClient, "request", fake_request)

    context = _context({"url": "https://example.com/flaky"}, {})
    with pytest.raises(RuntimeError, match="503"):
        await http_request_node.HttpRequestExecutor().execute(context)


# --------------------------------------------------------------------------
# condition.multi_branch
# --------------------------------------------------------------------------


async def test_multi_branch_config_requires_at_least_one_case() -> None:
    executor = multi_branch_node.MultiBranchExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config({"cases": []})


async def test_multi_branch_declared_output_handles_reflects_config() -> None:
    executor = multi_branch_node.MultiBranchExecutor()
    config = {
        "cases": [
            {"label": "refund", "field_path": "trigger.keyword", "value": "refund"},
            {"label": "cancel", "field_path": "trigger.keyword", "value": "cancel"},
        ]
    }
    assert executor.declared_output_handles(config) == ["refund", "cancel", "default"]


async def test_multi_branch_selects_first_matching_case_in_order() -> None:
    executor = multi_branch_node.MultiBranchExecutor()
    context = _context(
        {
            "cases": [
                {"label": "high", "field_path": "trigger.amount", "operator": "gt", "value": 100},
                {"label": "any", "field_path": "trigger.amount", "operator": "gte", "value": 0},
            ]
        },
        {"trigger": {"amount": 500}},
    )

    result = await executor.execute(context)

    assert result.selected_edge_handles == ["high"]
    assert result.output["matched_case"] == "high"


async def test_multi_branch_falls_back_to_default_when_nothing_matches() -> None:
    executor = multi_branch_node.MultiBranchExecutor()
    context = _context(
        {"cases": [{"label": "refund", "field_path": "trigger.keyword", "value": "refund"}]},
        {"trigger": {"keyword": "shipping"}},
    )

    result = await executor.execute(context)

    assert result.selected_edge_handles == ["default"]
    assert result.output["matched_case"] is None


# --------------------------------------------------------------------------
# data.transform
# --------------------------------------------------------------------------


async def test_data_transform_resolves_each_output_independently() -> None:
    executor = data_transform_node.DataTransformExecutor()
    context = _context(
        {"outputs": {"customer_name": "{{trigger.customer.name}}", "greeting": "Hi {{trigger.customer.name}}!"}},
        {"trigger": {"customer": {"name": "Asha"}}},
    )

    result = await executor.execute(context)

    assert isinstance(result, Success)
    assert result.output == {"customer_name": "Asha", "greeting": "Hi Asha!"}


async def test_data_transform_requires_at_least_one_output() -> None:
    executor = data_transform_node.DataTransformExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config({"outputs": {}})
