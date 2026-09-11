"""Offline unit tests for `flow.confirm` (composable-builder redesign,
Phase 4) - the fixed yes/no shortcut over the same send+suspend primitive
`whatsapp.ask_choice`/`whatsapp.ask_question` use.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Suspend
from fusionflow.modules.workflows.nodes import _whatsapp_common
from fusionflow.modules.workflows.nodes import flow_confirm as confirm_node

# No module-level `pytestmark` - this file mixes async execute()/
# extract_resume_value tests with one sync `_static_options` test, and
# `asyncio_mode = "auto"` (pyproject.toml) already auto-detects the
# coroutine ones without a marker.


def _fake_connector_instance(tenant_id: uuid.UUID) -> ConnectorInstance:
    return ConnectorInstance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_type_id=uuid.uuid4(),
        state=ConnectorState.CONNECTED,
        display_name="Test WhatsApp",
        provider_ref_ids={"phone_number_id": "stub-phone-1"},
    )


async def test_execute_sends_fixed_yes_no_buttons(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance:
        return instance

    async def fake_send_interactive_message(**kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(confirm_node.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="confirm_order",
        config={
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "question": "Shall I place this order?",
        },
        variables={"trigger": {"from": "15551234567"}},
    )

    result = await confirm_node.ConfirmExecutor().execute(context)

    assert isinstance(result, Suspend)
    assert result.correlation_key == "15551234567"
    assert calls[0]["buttons"] == [{"id": "yes", "title": "Yes"}, {"id": "no", "title": "No"}]


@pytest.mark.parametrize(
    ("resume_payload", "expected"),
    [
        ({"interactive": {"id": "yes", "title": "Yes"}}, {"id": "yes"}),
        ({"interactive": {"id": "no", "title": "No"}}, {"id": "no"}),
        ({"text": "Yeah"}, {"id": "yes"}),
        ({"text": "nope"}, {"id": "no"}),
        ({"text": "maybe later"}, {"id": None}),
        ({}, {"id": None}),
    ],
)
async def test_extract_resume_value_normalizes_taps_and_free_text(
    resume_payload: dict[str, Any], expected: dict[str, Any]
) -> None:
    value = await confirm_node.ConfirmExecutor().extract_resume_value({}, resume_payload)
    assert value == expected


def test_static_options_branch_source_is_always_the_fixed_yes_no_pair() -> None:
    assert confirm_node._static_options({}) == [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]
    assert confirm_node._static_options({"question": "anything"}) == [
        {"id": "yes", "label": "Yes"},
        {"id": "no", "label": "No"},
    ]
