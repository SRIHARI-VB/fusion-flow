"""Offline unit tests for `whatsapp.ask_question` (Phase 8 Part B) - the
first `can_suspend` node type. Same "no Postgres required" philosophy as
test_workflow_connector_nodes.py: `connector_service.get_instance` and the
WhatsApp adapter's send calls are monkeypatched.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Suspend
from fusionflow.modules.workflows.nodes import _whatsapp_common
from fusionflow.modules.workflows.nodes import whatsapp_ask_question as ask_node

pytestmark = pytest.mark.asyncio


def _fake_connector_instance(tenant_id: uuid.UUID) -> ConnectorInstance:
    return ConnectorInstance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_type_id=uuid.uuid4(),
        state=ConnectorState.CONNECTED,
        display_name="Test WhatsApp",
        provider_ref_ids={"phone_number_id": "stub-phone-1"},
    )


async def test_config_requires_input_type_and_question() -> None:
    executor = ask_node.AskQuestionExecutor()
    executor.validate_config(
        {
            "connector_instance_id": str(uuid.uuid4()),
            "to": "{{trigger.from}}",
            "input_type": "text",
            "question": "What size?",
        }
    )
    with pytest.raises(ValidationError):
        executor.validate_config({"connector_instance_id": str(uuid.uuid4()), "to": "x", "question": "y"})


async def test_registered_as_can_suspend_with_whatsapp_gate() -> None:
    executor = ask_node.AskQuestionExecutor()
    assert executor.can_suspend is True
    assert executor.required_connector_type_key == "whatsapp"
    assert executor.node_type == "whatsapp.ask_question"


async def test_execute_text_sends_text_message_and_returns_suspend(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = ask_node.AskQuestionExecutor()
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_text_message(*, instance: ConnectorInstance, to: str, body: str, session: Any) -> None:
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_node.whatsapp_adapter, "send_text_message", fake_send_text_message)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="ask_size",
        config={
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "input_type": "text",
            "question": "What size do you want?",
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await executor.execute(context)

    assert isinstance(result, Suspend)
    assert result.correlation_key == "15551234567"
    assert calls == [{"to": "15551234567", "body": "What size do you want?"}]


async def test_execute_buttons_calls_interactive_message_with_button_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = ask_node.AskQuestionExecutor()
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_interactive_message(
        *, instance, to, body_text, interactive_type, buttons=None, sections=None, list_button_label=None, session
    ) -> None:
        calls.append(
            {
                "to": to,
                "body_text": body_text,
                "interactive_type": interactive_type,
                "buttons": buttons,
                "sections": sections,
            }
        )

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_node.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="ask_payment_method",
        config={
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "input_type": "buttons",
            "question": "COD or prepaid?",
            "buttons": [{"id": "cod", "title": "COD"}, {"id": "prepaid", "title": "Prepaid"}],
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await executor.execute(context)

    assert isinstance(result, Suspend)
    assert result.correlation_key == "15551234567"
    assert calls[0]["interactive_type"] == "button"
    assert calls[0]["buttons"] == [{"id": "cod", "title": "COD"}, {"id": "prepaid", "title": "Prepaid"}]


async def test_execute_list_calls_interactive_message_with_sections_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = ask_node.AskQuestionExecutor()
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_interactive_message(
        *, instance, to, body_text, interactive_type, buttons=None, sections=None, list_button_label=None, session
    ) -> None:
        calls.append({"interactive_type": interactive_type, "sections": sections})

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_node.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="ask_color",
        config={
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "input_type": "list",
            "question": "Pick a color",
            "sections": [{"title": "Colors", "rows": [{"id": "red", "title": "Red"}]}],
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await executor.execute(context)

    assert isinstance(result, Suspend)
    assert calls[0]["interactive_type"] == "list"
    assert calls[0]["sections"] == [{"title": "Colors", "rows": [{"id": "red", "title": "Red", "description": None}]}]


async def test_extract_resume_value_text_reads_the_reply_text() -> None:
    executor = ask_node.AskQuestionExecutor()
    config = {
        "connector_instance_id": str(uuid.uuid4()),
        "to": "{{trigger.from}}",
        "input_type": "text",
        "question": "What is your shipping address?",
    }
    value = await executor.extract_resume_value(config, {"text": "221B Baker Street"})
    assert value == "221B Baker Street"


async def test_extract_resume_value_buttons_reads_the_tapped_button_id() -> None:
    executor = ask_node.AskQuestionExecutor()
    config = {
        "connector_instance_id": str(uuid.uuid4()),
        "to": "{{trigger.from}}",
        "input_type": "buttons",
        "question": "COD or prepaid?",
        "buttons": [{"id": "cod", "title": "COD"}, {"id": "prepaid", "title": "Prepaid"}],
    }
    value = await executor.extract_resume_value(config, {"interactive": {"id": "cod", "title": "COD"}})
    assert value == "cod"


async def test_extract_resume_value_list_reads_the_picked_row_id() -> None:
    executor = ask_node.AskQuestionExecutor()
    config = {
        "connector_instance_id": str(uuid.uuid4()),
        "to": "{{trigger.from}}",
        "input_type": "list",
        "question": "Pick a color",
        "sections": [{"title": "Colors", "rows": [{"id": "red", "title": "Red"}]}],
    }
    value = await executor.extract_resume_value(config, {"interactive": {"id": "red", "title": "Red"}})
    assert value == "red"


async def test_extract_resume_value_missing_reply_returns_none() -> None:
    executor = ask_node.AskQuestionExecutor()
    config = {
        "connector_instance_id": str(uuid.uuid4()),
        "to": "{{trigger.from}}",
        "input_type": "text",
        "question": "What is your shipping address?",
    }
    value = await executor.extract_resume_value(config, {})
    assert value is None
