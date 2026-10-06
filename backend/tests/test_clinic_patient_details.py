"""Exercise sequential patient prompts and booking snapshots with mocked I/O."""
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import httpx
import pytest

from fusionflow.modules.connectors.google import oauth
from fusionflow.modules.connectors.google_calendar.adapter import GoogleCalendarAdapter
from fusionflow.modules.workflows.engine import entitlement
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.run_loop import execute_run, resume_run
from fusionflow.modules.workflows.models import RunStatus, WorkflowRun
from fusionflow.modules.workflows.nodes import instagram_collect_text as collect, record_upsert
from scripts.upgrade_clinic_patient_details import NAME_STEPS, CALENDAR_STEPS, patient_details_graph, RepairError
from tests.test_clinic_instagram_repair import MemorySession, node, edge
from tests.test_google_calendar_reconnect import mock_http


@pytest.fixture
def patient_graph():
    nodes, edges = [], []
    for ask, save in NAME_STEPS.items():
        nodes.extend([
            node(ask, "instagram.collect_text", question="Who is this consultation for? What's the patient's name?",
                connector_instance_id=str(uuid.uuid4()), recipient_id="{{trigger.from}}"),
            node(save, "records.upsert", module="customers", operation="update",
                item_id="{{find-or-create-customer-pb.customer.id}}", fields={"name": "{{" + ask + ".reply}}"}),
            node("after-" + save, "log.noop", message="Continue booking"),
        ])
        edges.extend([edge(ask, save), edge(save, "after-" + save)])
    for i, booking_id in enumerate(list(CALENDAR_STEPS) + [f"requested-{j}" for j in range(15)]):
        nodes.append(node(booking_id, "records.upsert", module="appointment", operation="create", fields={
            "customer_id": "{{find-or-create-customer-pb.customer.id}}", "customer_name": "{{find-or-create-customer-pb.customer.name}}",
            "service": "Patient: {{find-or-create-customer-pb.customer.name}}", "status": "confirmed" if i < 3 else "requested",
        }))
        before = "before-" + booking_id
        nodes.append(node(before, "log.noop", message="Ready to book"))
        calendar_id = CALENDAR_STEPS.get(booking_id)
        if calendar_id:
            nodes.append(node(calendar_id, "connector.action", connector_instance_id=str(uuid.uuid4()), action="create_event",
                params={"description": "Patient: {{find-or-create-customer-pb.customer.name}}"}))
            edges.extend([edge(before, calendar_id), edge(calendar_id, booking_id)])
        else:
            edges.append(edge(before, booking_id))
    for n in nodes:
        n["type"] = "action"
        n["position"] = {"x": 0, "y": 0}
        n["data"]["label"] = "Patient Name"
    return {"nodes": nodes, "edges": edges}


@pytest.mark.parametrize("ask_id,save_id", NAME_STEPS.items())
async def test_each_branch_asks_name_then_phone_and_saves_before_continuing(patient_graph, ask_id, save_id, monkeypatch):
    fixed = patient_details_graph(patient_graph)
    phone_id = ask_id.replace("name", "phone")
    phone_save = save_id.replace("name", "phone")
    ids = {ask_id, save_id, phone_id, phone_save, "after-" + save_id}
    graph = {"nodes": [node("trigger", "manual.test_trigger")] + [n for n in fixed["nodes"] if n["id"] in ids],
        "edges": [edge("trigger", ask_id)] + [e for e in fixed["edges"] if e["source"] in ids and e["target"] in ids]}
    send = AsyncMock()
    update = AsyncMock(return_value={"id": str(uuid.uuid4())})
    monkeypatch.setattr(collect.connector_service, "get_instance", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(collect, "find_pending_wait", AsyncMock(return_value=None))
    monkeypatch.setattr(collect.instagram_adapter, "send_direct_message", send)
    monkeypatch.setattr(record_upsert, "resolve_adapter", AsyncMock(return_value=SimpleNamespace(update=update)))
    monkeypatch.setattr(entitlement, "first_block_message", AsyncMock(return_value=None))
    # The original find-customer output predates answers, as in a real run.
    session = MemorySession()
    run = WorkflowRun(id=uuid.uuid4(), tenant_id=uuid.uuid4(), workflow_id=uuid.uuid4(), workflow_version_id=uuid.uuid4(),
        status=RunStatus.RUNNING, started_at=datetime.now(timezone.utc), loop_guard_count=0)
    compiled = WorkflowGraph.from_json(graph)
    await execute_run(session, run, compiled, trigger_payload={"from": "patient"})
    assert run.waiting_node_id == ask_id
    assert [c.kwargs["text"] for c in send.call_args_list] == ["What is the patient's full name?"]
    run.waiting_variables["find-or-create-customer-pb"] = {"customer": {"id": str(uuid.uuid4())}}
    await resume_run(session, run, compiled, reply_payload={"text": "Test Patient"})
    assert run.waiting_node_id == phone_id and update.await_count == 1
    assert update.call_args.kwargs["fields"] == {"name": "Test Patient"}
    assert send.await_count == 2 and "phone number" in send.call_args.kwargs["text"]
    await resume_run(session, run, compiled, reply_payload={"text": "+919876543210"})
    assert run.status == RunStatus.COMPLETED and send.await_count == 2
    assert update.call_args.kwargs["fields"] == {"phone": "+919876543210"}


def test_all_booking_paths_use_fresh_name_phone_and_calendar_links(patient_graph):
    original = deepcopy(patient_graph)
    fixed = patient_details_graph(patient_graph)
    assert patient_graph == original and patient_details_graph(fixed) == fixed
    nodes = {n["id"]: n for n in fixed["nodes"]}
    bookings = [n for n in fixed["nodes"] if n["data"]["config"].get("module") == "appointment"]
    assert len(bookings) == 18
    for booking in bookings:
        lookup = "patient-details-" + booking["id"]
        fields = booking["data"]["config"]["fields"]
        assert fields["customer_name"] == "{{" + lookup + ".item.name}}"
        assert fields["customer_phone"] == "{{" + lookup + ".item.phone}}"
        assert nodes[lookup]["data"]["config"]["module"] == "customers"
        if booking["id"] in CALENDAR_STEPS:
            cal = CALENDAR_STEPS[booking["id"]]
            assert fields["calendar_event_id"] == "{{" + cal + ".id}}"
            assert "Phone: " in nodes[cal]["data"]["config"]["params"]["description"]
    patient_graph["nodes"] = [n for n in patient_graph["nodes"] if n["id"] != "requested-14"]
    with pytest.raises((RepairError, KeyError)):
        patient_details_graph(patient_graph)


@pytest.mark.parametrize("status", [204, 404, 410])
async def test_calendar_delete_succeeds_if_event_already_gone(monkeypatch, status):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status)
    mock_http(monkeypatch, respond)
    monkeypatch.setattr(oauth, "get_valid_access_token", AsyncMock(return_value="test-token"))
    await GoogleCalendarAdapter().delete_event(SimpleNamespace(), MemorySession(), event_id="event1")
    assert calls[0].method == "DELETE" and calls[0].url.path.endswith("/events/event1")


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_calendar_delete_never_claims_success_on_provider_error(monkeypatch, status):
    mock_http(monkeypatch, lambda request: httpx.Response(status))
    monkeypatch.setattr(oauth, "get_valid_access_token", AsyncMock(return_value="test-token"))
    with pytest.raises(httpx.HTTPStatusError):
        await GoogleCalendarAdapter().delete_event(SimpleNamespace(), MemorySession(), event_id="event1")


def test_historical_missing_phone_is_not_replaced_by_a_later_patient_contact():
    from fusionflow.modules.clinic_queue.models import PatientVisit
    from fusionflow.modules.clinic_queue.service import to_patient_visit_out_dict

    visit = PatientVisit(patient_name="Earlier Patient", patient_phone=None)
    customer = SimpleNamespace(name="Later Patient", phone="9999999999")
    result = to_patient_visit_out_dict(visit, customer=customer, doctor_name=None, include_notes=False)
    assert result["customer_name"] == "Earlier Patient" and result["customer_phone"] is None
