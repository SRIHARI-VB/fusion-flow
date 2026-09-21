"""Offline unit tests for Phase 5's new WhatsApp workflow node executors:
2 triggers (`whatsapp.interactive_reply_received`, `whatsapp.message_status_updated`)
and the unified `whatsapp.send_message` action's non-text content branches
(media, location, contact, buttons, list, template) - the text branch is
covered in `test_workflow_connector_nodes.py`.

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
from fusionflow.modules.workflows.nodes import whatsapp_send_message as send_message_node

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
# whatsapp.send_message - content_type="media"
# --------------------------------------------------------------------------


async def test_send_media_requires_url_or_id() -> None:
    executor = send_message_node.SendMessageExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config(
            {
                "connector_instance_id": str(uuid.uuid4()),
                "to": "1",
                "content": {"content_type": "media", "media_type": "image"},
            }
        )


async def test_send_media_calls_adapter_with_interpolated_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_media_message(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_message_node.whatsapp_adapter, "send_media_message", fake_send_media_message)

    context = ExecutionContext(
        session=None, tenant_id=tenant_id, run_id=uuid.uuid4(), node_id="n",
        config={
            "connector_instance_id": str(instance.id), "to": "{{trigger.from}}",
            "content": {
                "content_type": "media", "media_type": "image",
                "media_url": "https://example.com/pic.jpg", "caption": "hi {{trigger.from}}",
            },
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await send_message_node.SendMessageExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["to"] == "15551234567"
    assert calls[0]["caption"] == "hi 15551234567"
    assert calls[0]["media_type"] == "image"


async def test_send_media_missing_connector_instance_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)

    context = _context(
        {
            "connector_instance_id": str(uuid.uuid4()), "to": "1",
            "content": {"content_type": "media", "media_type": "image", "media_url": "https://x/y.jpg"},
        },
        {},
    )
    result = await send_message_node.SendMessageExecutor().execute(context)

    assert isinstance(result, Failure)
    assert "not found" in result.error


# --------------------------------------------------------------------------
# whatsapp.send_message - content_type="location"
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
    monkeypatch.setattr(send_message_node.whatsapp_adapter, "send_location_message", fake_send_location_message)

    context = _context(
        {
            "connector_instance_id": str(instance.id), "to": "1",
            "content": {"content_type": "location", "latitude": 12.9, "longitude": 77.5},
        },
        {},
        session=None,
    )
    result = await send_message_node.SendMessageExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["latitude"] == 12.9


# --------------------------------------------------------------------------
# whatsapp.send_message - content_type="contact"
# --------------------------------------------------------------------------


async def test_send_contact_requires_at_least_one_contact() -> None:
    executor = send_message_node.SendMessageExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config(
            {
                "connector_instance_id": str(uuid.uuid4()), "to": "1",
                "content": {"content_type": "contact", "contacts": []},
            }
        )


async def test_send_contact_calls_adapter_with_contact_list(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_contact_message(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_message_node.whatsapp_adapter, "send_contact_message", fake_send_contact_message)

    context = _context(
        {
            "connector_instance_id": str(instance.id), "to": "1",
            "content": {"content_type": "contact", "contacts": [{"name": "Asha", "phone": "1"}]},
        },
        {},
    )
    result = await send_message_node.SendMessageExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["contacts"] == [{"name": "Asha", "phone": "1"}]


# --------------------------------------------------------------------------
# whatsapp.send_message - content_type="buttons" / "list"
# --------------------------------------------------------------------------


async def test_send_interactive_buttons_rejects_more_than_three() -> None:
    executor = send_message_node.SendMessageExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config(
            {
                "connector_instance_id": str(uuid.uuid4()), "to": "1",
                "content": {
                    "content_type": "buttons", "body_text": "pick",
                    "buttons": [{"id": str(i), "title": str(i)} for i in range(4)],
                },
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
    monkeypatch.setattr(send_message_node.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)

    context = _context(
        {
            "connector_instance_id": str(instance.id), "to": "1",
            "content": {
                "content_type": "buttons", "body_text": "pick one",
                "buttons": [{"id": "yes", "title": "Yes"}, {"id": "no", "title": "No"}],
            },
        },
        {},
    )
    result = await send_message_node.SendMessageExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["interactive_type"] == "button"
    assert calls[0]["buttons"] == [{"id": "yes", "title": "Yes"}, {"id": "no", "title": "No"}]


async def test_send_interactive_list_rejects_more_than_ten_rows_total() -> None:
    executor = send_message_node.SendMessageExecutor()
    with pytest.raises(ValidationError):
        executor.validate_config(
            {
                "connector_instance_id": str(uuid.uuid4()), "to": "1",
                "content": {
                    "content_type": "list", "body_text": "pick",
                    "sections": [
                        {"title": "A", "rows": [{"id": str(i), "title": str(i)} for i in range(6)]},
                        {"title": "B", "rows": [{"id": str(i), "title": str(i)} for i in range(6, 11)]},
                    ],
                },
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
    monkeypatch.setattr(send_message_node.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)

    context = _context(
        {
            "connector_instance_id": str(instance.id), "to": "1",
            "content": {
                "content_type": "list", "body_text": "pick",
                "sections": [{"title": "Support", "rows": [{"id": "billing", "title": "Billing"}]}],
            },
        },
        {},
    )
    result = await send_message_node.SendMessageExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["interactive_type"] == "list"
    assert calls[0]["sections"][0]["title"] == "Support"


# --------------------------------------------------------------------------
# whatsapp.send_message - content_type="template"
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
    monkeypatch.setattr(send_message_node.whatsapp_adapter, "send_template_message", fake_send_template_message)

    context = _context(
        {
            "connector_instance_id": str(instance.id), "to": "1",
            "content": {
                "content_type": "template", "template_name": "order_confirmation",
                "language_code": "en_US", "body_variables": ["Asha", "#1234"],
            },
        },
        {},
        session=_FakeSessionNoTemplate(),
    )
    result = await send_message_node.SendMessageExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["template_name"] == "order_confirmation"
    assert calls[0]["body_variables"] == ["Asha", "#1234"]


async def test_send_template_passes_through_media_header_and_button_params(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_template_message(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_message_node.whatsapp_adapter, "send_template_message", fake_send_template_message)

    context = _context(
        {
            "connector_instance_id": str(instance.id), "to": "1",
            "content": {
                "content_type": "template", "template_name": "seasonal_promo",
                "language_code": "en_US", "header_media_type": "image",
                "header_media_url": "https://example.com/promo.jpg",
                "button_url_params": ["abc123"],
            },
        },
        {},
        session=_FakeSessionNoTemplate(),
    )
    result = await send_message_node.SendMessageExecutor().execute(context)

    assert isinstance(result, Success)
    assert calls[0]["header_media_type"] == "image"
    assert calls[0]["header_media_url"] == "https://example.com/promo.jpg"
    assert calls[0]["header_variable"] is None
    assert calls[0]["button_url_params"] == ["abc123"]


async def test_template_content_rejects_text_and_media_header_together() -> None:
    with pytest.raises(ValidationError):
        send_message_node.SendMessageConfig.model_validate(
            {
                "connector_instance_id": str(uuid.uuid4()),
                "to": "1",
                "content": {
                    "content_type": "template", "template_name": "x", "language_code": "en_US",
                    "header_variable": "Asha", "header_media_type": "image", "header_media_url": "https://x",
                },
            }
        )


async def test_template_content_rejects_media_header_without_url_or_id() -> None:
    with pytest.raises(ValidationError):
        send_message_node.SendMessageConfig.model_validate(
            {
                "connector_instance_id": str(uuid.uuid4()),
                "to": "1",
                "content": {
                    "content_type": "template", "template_name": "x", "language_code": "en_US",
                    "header_media_type": "image",
                },
            }
        )


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
            "connector_instance_id": str(instance.id), "to": "1",
            "content": {
                "content_type": "template", "template_name": "order_confirmation",
                "language_code": "en_US", "body_variables": ["OnlyOne"],
            },
        },
        {},
        session=_FakeSessionWithTemplate(),
    )
    result = await send_message_node.SendMessageExecutor().execute(context)

    assert isinstance(result, Failure)
    assert "expects 2 body variable" in result.error
