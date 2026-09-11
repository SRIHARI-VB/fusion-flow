"""Offline unit tests for `whatsapp.ask_via_template` — the template-send
equivalent of `whatsapp.ask_question`'s pause/resume mechanic (see that
node's module docstring for why it exists: a workflow triggered by a
non-WhatsApp event has no guaranteed open 24-hour session, so its first
outbound message must be a template, but it may still need to wait for a
reply). Same "no Postgres required" philosophy and fake-session shapes as
`test_workflow_whatsapp_nodes.py`'s `whatsapp.send_template` tests.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Suspend
from fusionflow.modules.workflows.nodes import _whatsapp_common
from fusionflow.modules.workflows.nodes import whatsapp_ask_via_template as ask_via_template_node

pytestmark = pytest.mark.asyncio


def _fake_instance(tenant_id: uuid.UUID) -> ConnectorInstance:
    return ConnectorInstance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_type_id=uuid.uuid4(),
        state=ConnectorState.CONNECTED,
        display_name="Test WhatsApp",
        provider_ref_ids={"phone_number_id": "stub-phone-1"},
    )


def _context(config: dict[str, Any], variables: dict[str, Any], session: Any = None) -> ExecutionContext:
    return ExecutionContext(
        session=session,
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="ask_rating",
        config=config,
        variables=variables,
    )


class _FakeSessionNoTemplate:
    """No local WhatsAppTemplate row - the variable-count cross-check
    should be skipped entirely, not fail (same shape as
    `test_workflow_whatsapp_nodes.py`'s `_FakeSessionNoTemplate`)."""

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        class _Result:
            def scalar_one_or_none(self_inner) -> None:
                return None

        return _Result()


async def test_registered_as_can_suspend_with_whatsapp_gate() -> None:
    executor = ask_via_template_node.AskViaTemplateExecutor()
    assert executor.can_suspend is True
    assert executor.required_connector_type_key == "whatsapp"
    assert executor.node_type == "whatsapp.ask_via_template"


async def test_execute_sends_template_then_returns_suspend(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_template_message(**kwargs: Any) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(ask_via_template_node.whatsapp_adapter, "send_template_message", fake_send_template_message)

    context = _context(
        {
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "template_name": "post_purchase_rating",
            "language_code": "en_US",
            "body_variables": ["Asha"],
        },
        {"trigger": {"from": "15551234567"}},
        session=_FakeSessionNoTemplate(),
    )

    result = await ask_via_template_node.AskViaTemplateExecutor().execute(context)

    assert isinstance(result, Suspend)
    assert result.correlation_key == "15551234567"
    assert calls[0]["template_name"] == "post_purchase_rating"
    assert calls[0]["body_variables"] == ["Asha"]


async def test_extract_resume_value_returns_raw_text() -> None:
    value = await ask_via_template_node.AskViaTemplateExecutor().extract_resume_value(
        {}, {"text": "5"}
    )
    assert value == "5"


async def test_extract_resume_value_missing_text_returns_none() -> None:
    value = await ask_via_template_node.AskViaTemplateExecutor().extract_resume_value({}, {})
    assert value is None
