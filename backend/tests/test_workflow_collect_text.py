"""Offline unit tests for `whatsapp.collect_text` (composable-builder
redesign, Phase 4) - a friendly text-only front door that delegates its
actual send+suspend logic to `whatsapp.ask_question`'s own executor
unchanged (see that module's import in `whatsapp_collect_text.py`), so
these tests monkeypatch the *ask_question* module's adapter reference,
not a copy owned by this node.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Suspend
from fusionflow.modules.workflows.nodes import _whatsapp_common
from fusionflow.modules.workflows.nodes import whatsapp_ask_question as ask_question_node
from fusionflow.modules.workflows.nodes import whatsapp_collect_text as collect_text_node

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


async def test_execute_delegates_to_ask_question_as_text(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance:
        return instance

    async def fake_send_text_message(*, instance, to, body, session) -> None:
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_question_node.whatsapp_adapter, "send_text_message", fake_send_text_message)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="collect_address",
        config={
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "question": "What's your delivery address?",
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await collect_text_node.CollectTextExecutor().execute(context)

    assert isinstance(result, Suspend)
    assert result.correlation_key == "15551234567"
    assert calls == [{"to": "15551234567", "body": "What's your delivery address?"}]


async def test_extract_resume_value_returns_raw_text() -> None:
    value = await collect_text_node.CollectTextExecutor().extract_resume_value(
        {}, {"text": "221B Baker Street"}
    )
    assert value == "221B Baker Street"


async def test_extract_resume_value_missing_text_returns_none() -> None:
    value = await collect_text_node.CollectTextExecutor().extract_resume_value({}, {})
    assert value is None
