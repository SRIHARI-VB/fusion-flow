"""Offline unit tests for Phase 5's 8 new WhatsApp workflow node executors:
2 triggers (`whatsapp.interactive_reply_received`, `whatsapp.message_status_updated`)
and 6 actions (`whatsapp.send_media`, `.send_location`, `.send_contact`,
`.send_interactive_buttons`, `.send_interactive_list`, `.send_template`).

Same "no Postgres required" philosophy as `test_workflow_connector_nodes.py`:
`connector_service.get_instance` (via `_whatsapp_common.resolve_whatsapp_instance`)
and each `whatsapp_adapter.send_*` call are monkeypatched.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.nodes import _whatsapp_common
from fusionflow.modules.workflows.nodes import whatsapp_interactive_reply_received as interactive_trigger_node
from fusionflow.modules.workflows.nodes import whatsapp_message_status_updated as status_trigger_node
from fusionflow.modules.workflows.nodes import whatsapp_send_contact as send_contact_node
from fusionflow.modules.workflows.nodes import whatsapp_send_interactive_buttons as send_buttons_node
from fusionflow.modules.workflows.nodes import whatsapp_send_interactive_list as send_list_node
from fusionflow.modules.workflows.nodes import whatsapp_send_location as send_location_node
from fusionflow.modules.workflows.nodes import whatsapp_send_media as send_media_node
from fusionflow.modules.workflows.nodes import whatsapp_send_template as send_template_node

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
# Triggers
# --------------------------------------------------------------------------


async def test_interactive_reply_received_echoes_trigger_payload() -> None:
    executor = interactive_trigger_node.WhatsAppInteractiveReplyReceivedExecutor()
    payload = {"from": "1", "message_id": "wamid.1", "interactive": {"type": "button_reply", "id": "yes", "title": "Yes"}}
    context = _context({}, {"trigger": payload})

    result = await executor.execute(context)

    assert isinstance(result, Success)
    assert result.output == payload


async def test_message_status_updated_echoes_trigger_payload() -> None:
    executor = status_trigger_node.WhatsAppMessageStatusUpdatedExecutor()
    payload = {"message_id": "wamid.1", "status": "delivered", "recipient_id": "1", "error": None}
    context = _context({}, {"trigger": payload})

    result = await executor.execute(context)

    assert isinstance(result, Success)
    assert result.output == payload


# --------------------------------------------------------------------------
# whatsapp.send_media
# --------------------------------------------------------------------------


async def test_send_media_requires_url_or_id() -> None:
    executor = send_media_node.SendMediaExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config({"connector_instance_id": str(uuid.uuid4()), "to": "1", "media_type": "image"})


async def test_send_media_calls_adapter_with_interpolated_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_media_message(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_media_node.whatsapp_adapter, "send_media_message", fake_send_media_message)

    context = ExecutionContext(
        session=None, tenant_id=tenant_id, run_id=uuid.uuid4(), node_id="n",
        config={
            "connector_instance_id": str(instance.id), "to": "{{trigger.from}}", "media_type": "image",
            "media_url": "https://example.com/pic.jpg", "caption": "hi {{trigger.from}}",
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await send_media_node.SendMediaExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["to"] == "15551234567"
    assert calls[0]["caption"] == "hi 15551234567"
    assert calls[0]["media_type"] == "image"


async def test_send_media_missing_connector_instance_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)

    context = _context(
        {"connector_instance_id": str(uuid.uuid4()), "to": "1", "media_type": "image", "media_url": "https://x/y.jpg"}, {}
    )
    result = await send_media_node.SendMediaExecutor().execute(context)

    assert isinstance(result, Failure)
    assert "not found" in result.error


# --------------------------------------------------------------------------
# whatsapp.send_location
# --------------------------------------------------------------------------


async def test_send_location_calls_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_location_message(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_location_node.whatsapp_adapter, "send_location_message", fake_send_location_message)

    context = _context(
        {"connector_instance_id": str(instance.id), "to": "1", "latitude": 12.9, "longitude": 77.5}, {},
        session=None,
    )
    result = await send_location_node.SendLocationExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["latitude"] == 12.9


# --------------------------------------------------------------------------
# whatsapp.send_contact
# --------------------------------------------------------------------------


async def test_send_contact_requires_at_least_one_contact() -> None:
    executor = send_contact_node.SendContactExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config({"connector_instance_id": str(uuid.uuid4()), "to": "1", "contacts": []})


async def test_send_contact_calls_adapter_with_contact_list(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_contact_message(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_contact_node.whatsapp_adapter, "send_contact_message", fake_send_contact_message)

    context = _context(
        {"connector_instance_id": str(instance.id), "to": "1", "contacts": [{"name": "Asha", "phone": "1"}]}, {},
    )
    result = await send_contact_node.SendContactExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["contacts"] == [{"name": "Asha", "phone": "1"}]


# --------------------------------------------------------------------------
# whatsapp.send_interactive_buttons / send_interactive_list
# --------------------------------------------------------------------------


async def test_send_interactive_buttons_rejects_more_than_three() -> None:
    executor = send_buttons_node.SendInteractiveButtonsExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config(
            {
                "connector_instance_id": str(uuid.uuid4()), "to": "1", "body_text": "pick",
                "buttons": [{"id": str(i), "title": str(i)} for i in range(4)],
            }
        )


async def test_send_interactive_buttons_calls_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_interactive_message(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_buttons_node.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)

    context = _context(
        {
            "connector_instance_id": str(instance.id), "to": "1", "body_text": "pick one",
            "buttons": [{"id": "yes", "title": "Yes"}, {"id": "no", "title": "No"}],
        },
        {},
    )
    result = await send_buttons_node.SendInteractiveButtonsExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["interactive_type"] == "button"
    assert calls[0]["buttons"] == [{"id": "yes", "title": "Yes"}, {"id": "no", "title": "No"}]


async def test_send_interactive_list_rejects_more_than_ten_rows_total() -> None:
    executor = send_list_node.SendInteractiveListExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config(
            {
                "connector_instance_id": str(uuid.uuid4()), "to": "1", "body_text": "pick",
                "sections": [
                    {"title": "A", "rows": [{"id": str(i), "title": str(i)} for i in range(6)]},
                    {"title": "B", "rows": [{"id": str(i), "title": str(i)} for i in range(6, 11)]},
                ],
            }
        )


async def test_send_interactive_list_calls_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_interactive_message(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_list_node.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)

    context = _context(
        {
            "connector_instance_id": str(instance.id), "to": "1", "body_text": "pick",
            "sections": [{"title": "Support", "rows": [{"id": "billing", "title": "Billing"}]}],
        },
        {},
    )
    result = await send_list_node.SendInteractiveListExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["interactive_type"] == "list"
    assert calls[0]["sections"][0]["title"] == "Support"


# --------------------------------------------------------------------------
# whatsapp.send_template
# --------------------------------------------------------------------------


class _FakeSessionNoTemplate:
    """No local WhatsAppTemplate row - the variable-count cross-check
    should be skipped entirely, not fail."""

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        class _Result:
            def scalar_one_or_none(self_inner) -> None:
                return None

        return _Result()


async def test_send_template_calls_adapter_when_no_local_template_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_template_message(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_template_node.whatsapp_adapter, "send_template_message", fake_send_template_message)

    context = _context(
        {
            "connector_instance_id": str(instance.id), "to": "1", "template_name": "order_confirmation",
            "language_code": "en_US", "body_variables": ["Asha", "#1234"],
        },
        {},
        session=_FakeSessionNoTemplate(),
    )
    result = await send_template_node.SendTemplateExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["template_name"] == "order_confirmation"
    assert calls[0]["body_variables"] == ["Asha", "#1234"]


class _FakeTemplate:
    components = {"body": {"text": "Hi {{1}}, order {{2}}", "variable_count": 2}}


class _FakeSessionWithTemplate:
    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        class _Result:
            def scalar_one_or_none(self_inner) -> Any:
                return _FakeTemplate()

        return _Result()


async def test_send_template_fails_clean_on_variable_count_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)

    context = _context(
        {
            "connector_instance_id": str(instance.id), "to": "1", "template_name": "order_confirmation",
            "language_code": "en_US", "body_variables": ["OnlyOne"],
        },
        {},
        session=_FakeSessionWithTemplate(),
    )
    result = await send_template_node.SendTemplateExecutor().execute(context)

    assert isinstance(result, Failure)
    assert "expects 2 body variable" in result.error
