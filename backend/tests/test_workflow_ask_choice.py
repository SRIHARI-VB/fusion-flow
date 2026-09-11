"""Offline unit tests for `whatsapp.ask_choice` (composable-builder redesign,
Phase 4) - same "no Postgres required" philosophy as
`test_workflow_ask_question.py`: the WhatsApp adapter's send calls and
`_whatsapp_common.connector_service.get_instance` are monkeypatched; a
module-sourced test monkeypatches `whatsapp_ask_choice.resolve_adapter`
directly (imported the same way `records.query`'s own tests monkeypatch
`module_registry.registry`/`resolve_adapter`).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Suspend
from fusionflow.modules.workflows.nodes import _whatsapp_common
from fusionflow.modules.workflows.nodes import whatsapp_ask_choice as ask_choice_node

# No module-level `pytestmark` here (unlike test_workflow_ask_question.py):
# this file mixes async execute()/extract_resume_value tests with plain
# sync `_static_options` tests, and `asyncio_mode = "auto"` (pyproject.toml)
# already auto-detects the coroutine ones without a marker - applying one
# unconditionally would spuriously warn on every sync test in this file.


def _fake_connector_instance(tenant_id: uuid.UUID) -> ConnectorInstance:
    return ConnectorInstance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_type_id=uuid.uuid4(),
        state=ConnectorState.CONNECTED,
        display_name="Test WhatsApp",
        provider_ref_ids={"phone_number_id": "stub-phone-1"},
    )


class _FakeModuleAdapter:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.captured: dict[str, Any] = {}

    async def list(self, session, *, tenant_id, filters, limit):
        self.captured["list"] = {"filters": filters, "limit": limit}
        return self.rows


def _static_config(*options: dict[str, str]) -> dict[str, Any]:
    return {
        "connector_instance_id": str(uuid.uuid4()),
        "to": "{{trigger.from}}",
        "question": "Pick one",
        "source": {"kind": "static", "options": list(options)},
    }


async def test_static_source_with_three_or_fewer_options_sends_buttons(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance:
        return instance

    async def fake_send_interactive_message(**kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_choice_node.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)

    config = _static_config({"id": "small", "label": "Small"}, {"id": "large", "label": "Large"})
    config["connector_instance_id"] = str(instance.id)
    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="ask_size",
        config=config,
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await ask_choice_node.AskChoiceExecutor().execute(context)

    assert isinstance(result, Suspend)
    assert result.correlation_key == "15551234567"
    assert calls[0]["interactive_type"] == "button"
    assert calls[0]["buttons"] == [{"id": "small", "title": "Small"}, {"id": "large", "title": "Large"}]


async def test_static_source_with_more_than_three_options_sends_a_list(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance:
        return instance

    async def fake_send_interactive_message(**kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_choice_node.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)

    options = [{"id": f"opt{i}", "label": f"Option {i}"} for i in range(4)]
    config = _static_config(*options)
    config["connector_instance_id"] = str(instance.id)
    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="ask_many",
        config=config,
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await ask_choice_node.AskChoiceExecutor().execute(context)

    assert isinstance(result, Suspend)
    assert calls[0]["interactive_type"] == "list"
    assert len(calls[0]["sections"][0]["rows"]) == 4


async def test_module_source_lists_from_the_resolved_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    adapter = _FakeModuleAdapter([{"id": "p1", "name": "Pizza"}, {"id": "p2", "name": "Burger"}])
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance:
        return instance

    async def fake_resolve_adapter(session, *, tenant_id, module_key) -> Any:
        assert module_key == "products"
        return adapter

    async def fake_send_interactive_message(**kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_choice_node, "resolve_adapter", fake_resolve_adapter)
    monkeypatch.setattr(ask_choice_node.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)

    context = ExecutionContext(
        session=object(),
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="ask_product",
        config={
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "question": "What would you like?",
            "source": {"kind": "module", "module": "products"},
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await ask_choice_node.AskChoiceExecutor().execute(context)

    assert isinstance(result, Suspend)
    assert calls[0]["buttons"] == [{"id": "p1", "title": "Pizza"}, {"id": "p2", "title": "Burger"}]


async def test_module_source_unknown_module_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance:
        return instance

    async def fake_resolve_adapter(session, *, tenant_id, module_key) -> Any:
        return None

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_choice_node, "resolve_adapter", fake_resolve_adapter)

    context = ExecutionContext(
        session=object(),
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="ask_product",
        config={
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "question": "What would you like?",
            "source": {"kind": "module", "module": "bogus"},
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await ask_choice_node.AskChoiceExecutor().execute(context)
    assert isinstance(result, Failure)
    assert "bogus" in result.error


async def test_extract_resume_value_reads_interactive_id_and_label() -> None:
    value = await ask_choice_node.AskChoiceExecutor().extract_resume_value(
        {}, {"interactive": {"id": "large", "title": "Large"}}
    )
    assert value == {"id": "large", "label": "Large"}


async def test_extract_resume_value_free_text_reply_has_no_id() -> None:
    value = await ask_choice_node.AskChoiceExecutor().extract_resume_value({}, {"text": "something else"})
    assert value == {"id": None, "label": None}


def test_static_options_branch_source_returns_options_for_static_source() -> None:
    config = _static_config({"id": "small", "label": "Small"}, {"id": "large", "label": "Large"})
    options = ask_choice_node._static_options(config)
    assert options == [{"id": "small", "label": "Small"}, {"id": "large", "label": "Large"}]


def test_static_options_branch_source_returns_none_for_module_source() -> None:
    config = {"source": {"kind": "module", "module": "products"}}
    assert ask_choice_node._static_options(config) is None


def test_static_options_branch_source_is_defensive_against_malformed_config() -> None:
    assert ask_choice_node._static_options({}) is None
    assert ask_choice_node._static_options({"source": "not-a-dict"}) is None
