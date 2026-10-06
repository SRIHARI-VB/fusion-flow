"""Clinic contact branches read settings at execution time, with mocked I/O."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from fusionflow.modules.workflows.engine import entitlement
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.run_loop import execute_run, resume_run
from fusionflow.modules.workflows.models import RunStatus, WorkflowRun
from fusionflow.modules.workflows.nodes import (
    connector_action, instagram_collect_text as collect, record_get_latest, record_upsert,
    schedule_resolve_business_hours as hours,
)
from scripts.upgrade_clinic_contact_details import RepairError, contact_details_graph
from tests.test_clinic_instagram_repair import MemorySession, node, edge


@pytest.fixture
def original_graph():
    connector_id = str(uuid.uuid4())
    def message(name, text):
        return node(name, "connector.action", connector_instance_id=connector_id,
                    action="send_direct_message", params={"recipient_id": "{{trigger.from}}", "text": text})
    def schedule(name, source):
        return node(name, "schedule.resolve_business_hours", timezone="Asia/Kolkata",
                    open_time="{{" + source + ".item.payload.open_time}}",
                    close_time="{{" + source + ".item.payload.close_time}}")
    nodes = [
        node("business-settings-pb", "records.get_latest", module="business_settings", filters={}),
        schedule("info-resolve-hours", "business-settings-pb"),
        schedule("resolve-emergency-hours-msg", "business-settings-msg"),
        node("info-cond-open-now", "condition.field_compare", field_path="info-resolve-hours.is_open_now", operator="eq", value=True),
        message("info-reply-open", "Open. Call: {{business-settings-pb.item.payload.phone}}"),
        message("info-reply-closed", "Closed. Call: {{business-settings-pb.item.payload.phone}}"),
        node("collect-issue-support-emergency", "instagram.collect_text", connector_instance_id=connector_id,
             recipient_id="{{trigger.from}}", question="Please briefly describe the emergency."),
        node("create-ticket-support-emergency", "records.upsert", module="tickets", operation="create",
             fields={"subject": "{{collect-issue-support-emergency.reply}}", "priority": "urgent"}),
        message("confirm-support-emergency", "Please call the clinic directly."),
        message("reply-emergency-outhours-1", "Closed until {{resolve-emergency-hours.next_open_date_display}}"),
    ]
    edges = [edge("info-resolve-hours", "info-cond-open-now"),
        edge("info-cond-open-now", "info-reply-open", "true"), edge("info-cond-open-now", "info-reply-closed", "false"),
        edge("collect-issue-support-emergency", "create-ticket-support-emergency"),
        edge("create-ticket-support-emergency", "confirm-support-emergency")]
    for entry, target in {"info-message": "info-resolve-hours", "info-button": "info-resolve-hours",
                          "support-button": "collect-issue-support-emergency",
                          "closed-message": "reply-emergency-outhours-1",
                          "closed-button": "reply-emergency-outhours-1"}.items():
        nodes.append(node(entry, "manual.test_trigger"))
        edges.append(edge(entry, target))
    for n in nodes:
        n["type"] = "action"
        n["position"] = {"x": 0, "y": 0}
        n["data"]["label"] = n["id"]
    return {"nodes": nodes, "edges": edges}


@pytest.fixture
def io(monkeypatch):
    payload = {"phone": "+910000000001", "open_time": "10:00", "close_time": "20:30"}
    lookup = AsyncMock(side_effect=lambda *a, **kw: [{"payload": dict(payload)}])
    monkeypatch.setattr(record_get_latest, "resolve_adapter", AsyncMock(return_value=SimpleNamespace(list=lookup)))
    send = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(connector_action.connector_service, "get_instance",
                        AsyncMock(return_value=SimpleNamespace(connector_type=SimpleNamespace(key="instagram"))))
    monkeypatch.setattr(connector_action.connector_registry, "get_or_none", lambda _: SimpleNamespace(perform_action=send))
    prompt = AsyncMock()
    monkeypatch.setattr(collect.instagram_adapter, "send_direct_message", prompt)
    monkeypatch.setattr(collect, "find_pending_wait", AsyncMock(return_value=None))
    create = AsyncMock(return_value={"id": "test-ticket"})
    monkeypatch.setattr(record_upsert, "resolve_adapter", AsyncMock(return_value=SimpleNamespace(create=create)))
    monkeypatch.setattr(entitlement, "first_block_message", AsyncMock(return_value=None))
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 7, 12, tzinfo=tz)
    monkeypatch.setattr(hours, "datetime", Clock)
    return SimpleNamespace(payload=payload, lookup=lookup, send=send, prompt=prompt, create=create)


async def start(graph, entry):
    # Only the selected event entry should run, just as the trigger index
    # selects one branch of the published clinic workflow.
    reachable = {entry}
    while True:
        targets = {e["target"] for e in graph["edges"] if e["source"] in reachable}
        if targets <= reachable:
            break
        reachable |= targets
    selected = {"nodes": [n for n in graph["nodes"] if n["id"] in reachable],
                "edges": [e for e in graph["edges"] if e["source"] in reachable]}
    compiled = WorkflowGraph.from_json(selected)
    run = WorkflowRun(id=uuid.uuid4(), tenant_id=uuid.uuid4(), workflow_id=uuid.uuid4(), workflow_version_id=uuid.uuid4(),
                      status=RunStatus.RUNNING, started_at=datetime.now(timezone.utc), loop_guard_count=0)
    session = MemorySession()
    await execute_run(session, run, compiled, trigger_payload={"from": "test-patient"})
    return run, session, compiled


@pytest.mark.parametrize("entry", ["info-message", "info-button"])
@pytest.mark.parametrize("open_now", [True, False])
async def test_info_uses_current_phone_from_either_entry(original_graph, io, entry, open_now):
    fixed = contact_details_graph(original_graph)
    if not open_now:
        io.payload["close_time"] = "11:00"
    for number in ("+910000000001", "+910000000002"):
        io.payload["phone"] = number
        run, _, _ = await start(fixed, entry)
        assert run.status == RunStatus.COMPLETED
        assert io.send.call_args.kwargs["params"]["text"] == f"{'Open' if open_now else 'Closed'}. Call: {number}"
    assert io.lookup.await_count == 2


async def test_emergency_prompt_and_confirmation_refresh_settings_after_reply(original_graph, io):
    run, session, compiled = await start(contact_details_graph(original_graph), "support-button")
    assert run.status == RunStatus.WAITING and run.waiting_node_id == "collect-issue-support-emergency"
    assert io.payload["phone"] in io.prompt.call_args.kwargs["text"]
    io.send.assert_not_awaited()
    io.payload["phone"] = "+910000000002"
    await resume_run(session, run, compiled, reply_payload={"text": "Test emergency"})
    assert run.status == RunStatus.COMPLETED
    assert io.create.call_args.kwargs["fields"] == {"subject": "Test emergency", "priority": "urgent"}
    io.send.assert_awaited_once()
    assert io.payload["phone"] in io.send.call_args.kwargs["params"]["text"]
    assert io.lookup.await_count == 2


@pytest.mark.parametrize("entry", ["closed-message", "closed-button"])
async def test_closed_emergency_includes_phone_and_a_resolved_date(original_graph, io, entry):
    run, _, _ = await start(contact_details_graph(original_graph), entry)
    assert run.status == RunStatus.COMPLETED
    text = io.send.call_args.kwargs["params"]["text"]
    assert io.payload["phone"] in text and "October" in text
    assert "{{" not in text and "on  for you" not in text


def test_upgrade_is_idempotent_and_does_not_mutate_input(original_graph):
    before = deepcopy(original_graph)
    fixed = contact_details_graph(original_graph)
    assert original_graph == before and contact_details_graph(fixed) == fixed


def test_upgrade_rejects_a_new_edge_bypassing_settings(original_graph):
    fixed = contact_details_graph(original_graph)
    fixed["edges"].append(edge("info-message", "info-resolve-hours"))
    with pytest.raises(RepairError, match="bypass"):
        contact_details_graph(fixed)
