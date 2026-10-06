"""Offline contract tests for the Instagram reset command and greeting."""

from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from fusionflow.modules.connectors.instagram.adapter import InstagramAdapter
from fusionflow.modules.inbox import service as inbox_service
from fusionflow.modules.workflows.engine import event_bus
from fusionflow.modules.workflows.engine.conversation_reset import event_time, is_clear_command
from scripts.repair_clinic_instagram_workflow import enable_reset_graph
from tests.test_clinic_instagram_repair import (
    MemorySession, edge, io, node, original_graph, run,
)


@pytest.mark.parametrize("text,expected", [
    ("/clear", True), (" /CLEAR \n", True), ("/Clear", True),
    ("please /clear", False), ("/clear all", False), ("clear", False), (None, False),
])
def test_exact_clear_command(text, expected):
    assert is_clear_command({"text": text}) is expected


@pytest.mark.parametrize("timestamp", [None, "bad", True, -1, float("inf")])
def test_invalid_provider_timestamp_falls_back_to_receipt(timestamp):
    now = datetime.now(timezone.utc)
    assert event_time(SimpleNamespace(payload={"timestamp": timestamp}, created_at=now)) == now


def test_provider_timestamp_survives_late_delivery():
    now = datetime.now(timezone.utc)
    assert event_time(SimpleNamespace(payload={"timestamp": 1000}, created_at=now)) == datetime.fromtimestamp(1, timezone.utc)


@pytest.fixture
def reset_graph(original_graph):
    # The production clinic router gives the reset flag precedence over any
    # ordinary intent, so even a non-greeting starts the initial welcome.
    original_graph["nodes"].append(node("intent-router", "condition.multi_branch", cases=[
        {"label": "greeting", "field_path": "trigger.text", "operator": "eq", "value": "Hi"},
    ]))
    original_graph["edges"] = [
        e for e in original_graph["edges"] if e["source"] != "find-or-create-customer-msg"
    ] + [edge("find-or-create-customer-msg", "intent-router"),
         edge("intent-router", "cond-first-time", "greeting")]
    return enable_reset_graph(original_graph)


@pytest.mark.parametrize("text", ["Hi", "I want to book an appointment"])
async def test_existing_patient_starts_initial_flow_after_reset(reset_graph, io, text):
    session = await run(reset_graph, text=text, conversation_reset=True)
    assert io.send.call_args.kwargs["params"]["text"] == "Welcome to our clinic!"
    customer_step = next(s for s in session.added if s.node_id == "find-or-create-customer-msg")
    assert customer_step.output["created"] is False
    assert "cond-first-time" not in [s.node_id for s in session.added]
    io.create.assert_not_awaited()
    io.history.assert_not_awaited()


async def test_existing_patient_without_reset_keeps_returning_menu(reset_graph, io):
    await run(reset_graph, text="Hi")
    assert io.send.call_args.kwargs["params"]["text"].startswith("Welcome back!")


async def test_new_patient_still_gets_initial_menu(reset_graph, io):
    io.lookup.return_value = None
    await run(reset_graph, text="Hi")
    assert io.send.call_args.kwargs["params"]["text"] == "Welcome to our clinic!"
    io.create.assert_awaited_once()


def test_graph_update_is_idempotent(reset_graph):
    assert enable_reset_graph(reset_graph) == reset_graph


async def test_webhook_queues_clear_and_hi_without_resolving_wait(monkeypatch):
    publish = AsyncMock()
    pending = AsyncMock(side_effect=AssertionError("Resume must be resolved by the ordered dispatcher"))
    monkeypatch.setattr(event_bus, "publish_trigger_event", publish)
    monkeypatch.setattr(event_bus, "find_pending_wait", pending)
    monkeypatch.setattr(inbox_service, "upsert_inbound_message", AsyncMock())
    instance = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4())
    adapter = InstagramAdapter()
    for index, text in enumerate(["/clear", "Hi"]):
        body = {"entry": [{"messaging": [{"sender": {"id": "sender"}, "timestamp": 1000 + index,
                                          "message": {"mid": f"mid-{index}", "text": text}}]}]}
        await adapter.handle_webhook(instance=instance, raw_payload=json.dumps(body).encode(),
                                     headers={}, session=MemorySession())
    pending.assert_not_awaited()
    assert [c.kwargs["payload"]["text"] for c in publish.call_args_list] == ["/clear", "Hi"]
    assert [c.kwargs["payload"]["timestamp"] for c in publish.call_args_list] == [1000, 1001]
    assert all(c.kwargs["event_type"] == "instagram.message_received" for c in publish.call_args_list)
    assert [c.kwargs["dedupe_key"] for c in publish.call_args_list] == ["mid-0", "mid-1"]
