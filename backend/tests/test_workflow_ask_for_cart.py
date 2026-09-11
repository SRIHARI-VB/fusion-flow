"""Offline unit tests for `whatsapp.ask_for_cart` (WhatsApp Commerce
Catalog cart support) - same "no Postgres required" philosophy as
`test_workflow_ask_choice.py`: the WhatsApp adapter's send call and
`_whatsapp_common.connector_service.get_instance` are monkeypatched;
`resolve_adapter` is monkeypatched directly the same way `whatsapp.
ask_choice`'s module-sourced tests do.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Suspend
from fusionflow.modules.workflows.nodes import _whatsapp_common
from fusionflow.modules.workflows.nodes import whatsapp_ask_for_cart as ask_for_cart_node


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

    async def list(self, session, *, tenant_id, filters, limit):
        return self.rows


async def test_execute_sends_product_list_and_suspends(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    adapter = _FakeModuleAdapter([{"id": "11111111-1111-1111-1111-111111111111", "name": "Pizza"}])
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance:
        return instance

    async def fake_resolve_adapter(session, *, tenant_id, module_key) -> Any:
        assert module_key == "products"
        return adapter

    async def fake_send_product_list_message(**kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_for_cart_node, "resolve_adapter", fake_resolve_adapter)
    monkeypatch.setattr(
        ask_for_cart_node.whatsapp_adapter, "send_product_list_message", fake_send_product_list_message
    )

    context = ExecutionContext(
        session=object(),
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="ask_for_cart",
        config={
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "catalog_id": "cat_123",
            "body_text": "Browse and add items",
            "module": "products",
            "filters": {},
            "limit": 30,
            "section_title": "Our Products",
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await ask_for_cart_node.AskForCartExecutor().execute(context)

    assert isinstance(result, Suspend)
    assert result.correlation_key == "15551234567"
    assert calls[0]["catalog_id"] == "cat_123"
    assert calls[0]["sections"] == [
        {
            "title": "Our Products",
            "product_items": [{"product_retailer_id": "11111111-1111-1111-1111-111111111111"}],
        }
    ]


async def test_execute_unknown_module_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance:
        return instance

    async def fake_resolve_adapter(session, *, tenant_id, module_key) -> Any:
        return None

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_for_cart_node, "resolve_adapter", fake_resolve_adapter)

    context = ExecutionContext(
        session=object(),
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="ask_for_cart",
        config={
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "catalog_id": "cat_123",
            "body_text": "Browse and add items",
            "module": "bogus",
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await ask_for_cart_node.AskForCartExecutor().execute(context)
    assert isinstance(result, Failure)
    assert "bogus" in result.error


async def test_extract_resume_value_returns_the_order_dict() -> None:
    order = {"catalog_id": "cat_123", "product_items": [{"product_retailer_id": "p1", "quantity": "2"}], "note": None}
    value = await ask_for_cart_node.AskForCartExecutor().extract_resume_value({}, {"order": order})
    assert value == order


async def test_extract_resume_value_returns_none_without_an_order() -> None:
    value = await ask_for_cart_node.AskForCartExecutor().extract_resume_value({}, {"text": "hello"})
    assert value is None
