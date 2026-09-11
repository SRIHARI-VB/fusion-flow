"""Offline unit tests for Phase 6's 3 new WhatsApp node executors
(`whatsapp.mark_as_read`, `.get_business_profile`, `.update_business_profile`)
and the standalone `whatsapp.find_or_create_customer` node, plus the 3
matching `WhatsAppAdapter.perform_action` dispatch branches.

Same "no Postgres required" philosophy as `test_workflow_whatsapp_nodes.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.nodes import _whatsapp_common
from fusionflow.modules.workflows.nodes import whatsapp_find_or_create_customer as find_or_create_node
from fusionflow.modules.workflows.nodes import whatsapp_get_business_profile as get_profile_node
from fusionflow.modules.workflows.nodes import whatsapp_mark_as_read as mark_read_node
from fusionflow.modules.workflows.nodes import whatsapp_update_business_profile as update_profile_node

pytestmark = pytest.mark.asyncio


def _context(config: dict[str, Any], variables: dict[str, Any]) -> ExecutionContext:
    return ExecutionContext(
        session=None,
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="node-under-test",
        config=config,
        variables=variables,
    )


def _fake_instance(tenant_id: uuid.UUID) -> ConnectorInstance:
    return ConnectorInstance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_type_id=uuid.uuid4(),
        state=ConnectorState.CONNECTED,
        display_name="Test WhatsApp",
        provider_ref_ids={"phone_number_id": "stub-phone-1"},
    )


# --------------------------------------------------------------------------
# whatsapp.mark_as_read
# --------------------------------------------------------------------------


async def test_mark_as_read_calls_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    captured: dict[str, Any] = {}

    async def fake_mark_as_read(*, instance: Any, message_id: str, session: Any) -> None:
        captured["message_id"] = message_id

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(mark_read_node.whatsapp_adapter, "mark_message_as_read", fake_mark_as_read)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="node",
        config={"connector_instance_id": str(instance.id), "message_id": "{{trigger.message_id}}"},
        variables={"trigger": {"message_id": "wamid.123"}},
    )

    result = await mark_read_node.MarkAsReadExecutor().execute(context)

    assert isinstance(result, Success)
    assert result.output == {"message_id": "wamid.123"}
    assert captured["message_id"] == "wamid.123"


async def test_mark_as_read_missing_instance_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)

    context = _context({"connector_instance_id": str(uuid.uuid4()), "message_id": "wamid.1"}, {})
    result = await mark_read_node.MarkAsReadExecutor().execute(context)

    assert isinstance(result, Failure)


# --------------------------------------------------------------------------
# whatsapp.get_business_profile / update_business_profile
# --------------------------------------------------------------------------


async def test_get_business_profile_returns_adapter_result(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_get_profile(*, instance: Any, session: Any) -> dict:
        return {"about": "We sell widgets"}

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(get_profile_node.whatsapp_adapter, "get_business_profile", fake_get_profile)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="node",
        config={"connector_instance_id": str(instance.id)},
        variables={},
    )

    result = await get_profile_node.GetBusinessProfileExecutor().execute(context)

    assert isinstance(result, Success)
    assert result.output == {"profile": {"about": "We sell widgets"}}


async def test_update_business_profile_passes_fields_through(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    captured: dict[str, Any] = {}

    async def fake_update_profile(*, instance: Any, profile_fields: dict, session: Any) -> dict:
        captured["profile_fields"] = profile_fields
        return profile_fields

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(update_profile_node.whatsapp_adapter, "update_business_profile", fake_update_profile)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="node",
        config={"connector_instance_id": str(instance.id), "profile_fields": {"about": "New about"}},
        variables={},
    )

    result = await update_profile_node.UpdateBusinessProfileExecutor().execute(context)

    assert isinstance(result, Success)
    assert result.output == {"profile": {"about": "New about"}}
    assert captured["profile_fields"] == {"about": "New about"}


# --------------------------------------------------------------------------
# whatsapp.find_or_create_customer
# --------------------------------------------------------------------------


async def test_find_or_create_customer_returns_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    from fusionflow.modules.customers.models import Customer

    existing = Customer(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        name="Asha",
        phone="15551234567",
        custom_fields={},
        created_at=datetime.now(timezone.utc),
    )

    async def fake_get_by_phone(session: Any, tenant_id: uuid.UUID, phone: str) -> Customer:
        assert phone == "15551234567"
        return existing

    monkeypatch.setattr(find_or_create_node.customers_service, "get_customer_by_phone", fake_get_by_phone)

    context = _context({"phone": "{{trigger.from}}"}, {"trigger": {"from": "15551234567"}})
    result = await find_or_create_node.FindOrCreateCustomerExecutor().execute(context)

    assert isinstance(result, Success)
    assert result.output["created"] is False
    assert result.output["customer"]["phone"] == "15551234567"


async def test_find_or_create_customer_creates_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    from fusionflow.modules.customers.models import Customer

    async def fake_get_by_phone(session: Any, tenant_id: uuid.UUID, phone: str) -> None:
        return None

    created_holder: dict[str, Any] = {}

    async def fake_create_customer(session: Any, tenant_id: uuid.UUID, payload: Any) -> Customer:
        created_holder["payload"] = payload
        return Customer(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            name=payload.name,
            phone=payload.phone,
            custom_fields={},
            created_at=datetime.now(timezone.utc),
        )

    monkeypatch.setattr(find_or_create_node.customers_service, "get_customer_by_phone", fake_get_by_phone)
    monkeypatch.setattr(find_or_create_node.customers_service, "create_customer", fake_create_customer)

    context = _context({"phone": "{{trigger.from}}"}, {"trigger": {"from": "15559999999"}})
    result = await find_or_create_node.FindOrCreateCustomerExecutor().execute(context)

    assert isinstance(result, Success)
    assert result.output["created"] is True
    assert result.output["customer"]["phone"] == "15559999999"
    assert created_holder["payload"].name == "15559999999"  # fell back to phone, no name given


# --------------------------------------------------------------------------
# WhatsAppAdapter.perform_action dispatch (stub mode - no real Graph API call)
# --------------------------------------------------------------------------


async def test_perform_action_mark_message_as_read_requires_message_id() -> None:
    instance = _fake_instance(uuid.uuid4())
    with pytest.raises(ValueError):
        await whatsapp_adapter.perform_action(
            action="mark_message_as_read", params={}, instance=instance, session=None
        )


async def test_perform_action_mark_message_as_read_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = _fake_instance(uuid.uuid4())
    captured: dict[str, Any] = {}

    async def fake_mark(*, instance: Any, message_id: str, session: Any) -> None:
        captured["message_id"] = message_id

    monkeypatch.setattr(whatsapp_adapter, "mark_message_as_read", fake_mark)
    output = await whatsapp_adapter.perform_action(
        action="mark_message_as_read", params={"message_id": "wamid.1"}, instance=instance, session=None
    )
    assert output == {"message_id": "wamid.1"}
    assert captured["message_id"] == "wamid.1"


async def test_perform_action_get_business_profile_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = _fake_instance(uuid.uuid4())

    async def fake_get_profile(*, instance: Any, session: Any) -> dict:
        return {"about": "hi"}

    monkeypatch.setattr(whatsapp_adapter, "get_business_profile", fake_get_profile)
    output = await whatsapp_adapter.perform_action(
        action="get_business_profile", params={}, instance=instance, session=None
    )
    assert output == {"about": "hi"}


async def test_perform_action_update_business_profile_dispatches(monkeypatch: pytest.MonkeyPatch) -> None:
    instance = _fake_instance(uuid.uuid4())
    captured: dict[str, Any] = {}

    async def fake_update_profile(*, instance: Any, profile_fields: dict, session: Any) -> dict:
        captured["profile_fields"] = profile_fields
        return profile_fields

    monkeypatch.setattr(whatsapp_adapter, "update_business_profile", fake_update_profile)
    output = await whatsapp_adapter.perform_action(
        action="update_business_profile", params={"profile_fields": {"about": "x"}}, instance=instance, session=None
    )
    assert output == {"about": "x"}
    assert captured["profile_fields"] == {"about": "x"}
