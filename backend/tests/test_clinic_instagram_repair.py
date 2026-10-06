"""Regression coverage for the clinic repair; all provider/record IO is mocked."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from fusionflow.modules.workflows import service
from fusionflow.modules.workflows.engine import entitlement
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.registry import Success, node_executor_registry
from fusionflow.modules.workflows.engine.run_loop import execute_run
from fusionflow.modules.workflows.models import RunStatus, WorkflowRun, WorkflowStatus
from fusionflow.modules.workflows.nodes import connector_action, instagram_find_or_create_customer
from fusionflow.modules.workflows.validation import ValidationIssue, ValidationResult
from scripts.repair_clinic_instagram_workflow import RepairError, repair_graph, repair_workflow


MENU_TEXT = (
    "Welcome back! How may I help you today?\n\n"
    "(Or just type your answer if you don't see buttons.)"
)
PAYLOADS = ["MENU_CONSULT", "MENU_TREATMENTS", "MENU_INFO", "MENU_SUPPORT"]
DIAGNOSTIC = "Unrecognised button tap - Instagram: test-sender - payload MENU_2"
CONNECTOR_ID = str(uuid.uuid4())


def node(node_id, node_type, **config):
    return {"id": node_id, "data": {"nodeType": node_type, "config": config}}


def edge(source, target, handle=None):
    return {"id": f"{source}-{target}", "source": source, "target": target, "sourceHandle": handle}


def menu(node_id, text):
    return node(node_id, "connector.action", connector_instance_id=CONNECTOR_ID,
                action="send_quick_replies", params={
                    "recipient_id": "{{trigger.from}}", "text": text,
                    "replies": [{"title": p, "payload": p} for p in PAYLOADS],
                })


@pytest.fixture
def original_graph():
    # Sanitized reproduction of the two affected branches. The four valid
    # clinic buttons have distinct terminal actions, so routing is observable.
    nodes = [
        node("trigger", "manual.test_trigger"),
        node("is-postback", "condition.field_compare", field_path="trigger.kind", operator="eq", value="postback"),
        node("find-or-create-customer-msg", "instagram.find_or_create_customer", external_ref="{{trigger.from}}"),
        node("cond-first-time", "condition.field_compare", field_path="find-or-create-customer-msg.created", operator="eq", value=True),
        menu("send-main-menu-firsttime", "Welcome to our clinic!"),
        menu("send-main-menu-returning", MENU_TEXT),
        node("personalize-lookup-last-ticket", "records.get_latest", module="tickets", filters={"customer_id": "{{find-or-create-customer-msg.customer.id}}"}),
        node("personalize-cond-has-history", "condition.field_compare", field_path="personalize-lookup-last-ticket.found", operator="eq", value=True),
        menu("personalize-send-main-menu-returning", "Welcome back! Last time you reached out to us about: {{personalize-lookup-last-ticket.item.subject}}\n\nHow may I help you today?"),
        node("pb-no-match", "log.noop", message="No case matched"),
        menu("reply-pb-fallback", "Let me check with our clinic team."),
        node("create-ticket-pb-fallback", "records.upsert", module="tickets", operation="create", fields={"subject": DIAGNOSTIC}),
        node("note-pb-fallback", "tickets.add_note", ticket_id="{{create-ticket-pb-fallback.item.id}}", body="Unrecognised payload"),
    ]
    edges = [
        edge("trigger", "is-postback"),
        edge("is-postback", "find-or-create-customer-msg", "false"),
        edge("find-or-create-customer-msg", "cond-first-time"),
        edge("cond-first-time", "send-main-menu-firsttime", "true"),
        edge("cond-first-time", "personalize-lookup-last-ticket", "false"),
        edge("personalize-lookup-last-ticket", "personalize-cond-has-history"),
        edge("personalize-cond-has-history", "personalize-send-main-menu-returning", "true"),
        edge("personalize-cond-has-history", "send-main-menu-returning", "false"),
        edge("pb-no-match", "reply-pb-fallback"),
        edge("reply-pb-fallback", "create-ticket-pb-fallback"),
        edge("create-ticket-pb-fallback", "note-pb-fallback"),
        edge("is-postback", "pb-0", "true"),
    ]
    for i, payload in enumerate(PAYLOADS):
        nodes += [node(f"pb-{i}", "condition.field_compare", field_path="trigger.payload", operator="eq", value=payload),
                  menu(f"reply-{i}", f"Handled {payload}")]
        edges += [edge(f"pb-{i}", f"reply-{i}", "true"),
                  edge(f"pb-{i}", f"pb-{i+1}" if i < 3 else "pb-no-match", "false")]
    return {"nodes": nodes, "edges": edges}


class MemorySession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass


@pytest.fixture
def io(monkeypatch):
    customer = SimpleNamespace(id=uuid.uuid4(), name="Test patient", external_ref="test-sender",
                               email=None, phone=None, custom_fields={}, created_at=datetime.now(timezone.utc))
    lookup = AsyncMock(return_value=customer)
    create = AsyncMock(return_value=customer)
    monkeypatch.setattr(instagram_find_or_create_customer.customers_service, "get_customer_by_external_ref", lookup)
    monkeypatch.setattr(instagram_find_or_create_customer.customers_service, "create_customer", create)
    history = AsyncMock(return_value=Success(output={"found": True, "item": {"subject": DIAGNOSTIC}}))
    monkeypatch.setattr(node_executor_registry.get("records.get_latest"), "execute", history)
    writes = AsyncMock(return_value=Success(output={"item": {"id": "test-ticket"}}))
    monkeypatch.setattr(node_executor_registry.get("records.upsert"), "execute", writes)
    monkeypatch.setattr(node_executor_registry.get("tickets.add_note"), "execute", writes)
    send = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(connector_action.connector_service, "get_instance", AsyncMock(
        return_value=SimpleNamespace(connector_type=SimpleNamespace(key="instagram"))))
    monkeypatch.setattr(connector_action.connector_registry, "get_or_none", lambda _: SimpleNamespace(perform_action=send))
    monkeypatch.setattr(entitlement, "first_block_message", AsyncMock(return_value=None))
    return SimpleNamespace(lookup=lookup, create=create, history=history, writes=writes, send=send)


async def run(graph, **payload):
    record = WorkflowRun(id=uuid.uuid4(), tenant_id=uuid.uuid4(), workflow_id=uuid.uuid4(),
                         workflow_version_id=uuid.uuid4(), status=RunStatus.RUNNING,
                         started_at=datetime.now(timezone.utc), loop_guard_count=0)
    session = MemorySession()
    await execute_run(session, record, WorkflowGraph.from_json(graph), trigger_payload={"from": "test-sender", **payload})
    assert record.status == RunStatus.COMPLETED
    return session


async def test_reproduces_old_greeting_then_removes_diagnostic_text(original_graph, io):
    await run(original_graph, text="Hi")
    assert DIAGNOSTIC in io.send.call_args.kwargs["params"]["text"]
    io.send.reset_mock()
    io.history.reset_mock()
    await run(repair_graph(original_graph), text="Hi")
    io.history.assert_not_awaited()
    io.send.assert_awaited_once()
    params = io.send.call_args.kwargs["params"]
    assert params["text"] == MENU_TEXT
    assert params["recipient_id"] == "test-sender"
    assert [r["payload"] for r in params["replies"]] == PAYLOADS
    io.create.assert_not_awaited()


async def test_new_customer_keeps_first_time_menu(original_graph, io):
    io.lookup.return_value = None
    await run(repair_graph(original_graph), text="Hi")
    io.create.assert_awaited_once()
    assert io.send.call_args.kwargs["params"]["text"] == "Welcome to our clinic!"
    io.history.assert_not_awaited()


@pytest.mark.parametrize("payload", ["MENU_2", "MENU_0", "UNRELATED_BUTTON"])
async def test_unknown_buttons_end_in_log_without_reply_or_ticket(original_graph, io, payload):
    session = await run(repair_graph(original_graph), kind="postback", payload=payload)
    assert session.added[-1].node_id == "pb-no-match"
    io.send.assert_not_awaited()
    io.writes.assert_not_awaited()


@pytest.mark.parametrize("payload", PAYLOADS)
async def test_supported_clinic_buttons_keep_their_routes(original_graph, io, payload):
    await run(repair_graph(original_graph), kind="postback", payload=payload)
    io.send.assert_awaited_once()
    assert io.send.call_args.kwargs["params"]["text"] == f"Handled {payload}"


def test_repair_is_idempotent_and_preserves_original(original_graph):
    snapshot = deepcopy(original_graph)
    fixed = repair_graph(original_graph)
    assert original_graph == snapshot
    assert repair_graph(fixed) == fixed


@pytest.mark.parametrize("drift", ["new_connection", "partial_repair", "downstream_reference", "edge_filter"])
def test_refuses_unreviewed_graph_changes(original_graph, drift):
    if drift == "new_connection":
        original_graph["edges"].append(edge("personalize-lookup-last-ticket", "reply-0"))
    elif drift == "partial_repair":
        original_graph["nodes"] = [n for n in original_graph["nodes"] if n["id"] != "note-pb-fallback"]
    elif drift == "downstream_reference":
        original_graph["nodes"].append(menu("other", "{{personalize-lookup-last-ticket.item.subject}}"))
    else:
        original_graph["edges"][4]["data"] = {"filter": {"field_path": "trigger.from", "value": "someone"}}
    with pytest.raises(RepairError):
        repair_graph(original_graph)


@pytest.fixture
def publishing(monkeypatch, original_graph):
    tenant_id, workflow_id, version_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    workflow = SimpleNamespace(id=workflow_id, status=WorkflowStatus.PUBLISHED, current_published_version_id=version_id)
    version = SimpleNamespace(id=version_id, version_number=32, graph=original_graph, published_at=datetime.now(timezone.utc))
    session = SimpleNamespace(execute=AsyncMock(side_effect=[
        SimpleNamespace(scalar_one_or_none=lambda: workflow),
        SimpleNamespace(scalar_one_or_none=lambda: uuid.uuid4()),
    ]))
    monkeypatch.setattr(service, "get_latest_version", AsyncMock(return_value=version))
    monkeypatch.setattr(service, "resolve_node_templates", AsyncMock(side_effect=lambda s, g: g))
    validation = AsyncMock(return_value=ValidationResult())
    monkeypatch.setattr(service, "validate_for_publish", validation)
    update = AsyncMock()
    publish = AsyncMock(return_value=(workflow, SimpleNamespace(id=uuid.uuid4(), version_number=33), ValidationResult()))
    monkeypatch.setattr(service, "update_workflow", update)
    monkeypatch.setattr(service, "publish_workflow", publish)
    return SimpleNamespace(session=session, workflow=workflow, version=version, validation=validation,
                           update=update, publish=publish, args=dict(tenant_id=tenant_id, workflow_id=workflow_id,
                           actor_email="owner@example.test", expected_version=32))


async def test_dry_run_validates_without_writes(publishing):
    p = publishing
    report = await repair_workflow(p.session, **p.args)
    assert report["result"] == "valid dry run; no writes"
    p.validation.assert_awaited_once()
    p.update.assert_not_awaited()
    p.publish.assert_not_awaited()


async def test_apply_uses_normal_version_and_publish_services(publishing):
    p = publishing
    before = deepcopy(p.version.graph)
    report = await repair_workflow(p.session, **p.args, apply=True)
    assert report["published_version"] == 33
    p.publish.assert_awaited_once()
    assert p.update.call_args.kwargs["graph"] == repair_graph(before)
    assert p.version.graph == before


@pytest.mark.parametrize("reason", ["draft", "version_changed", "validation"])
async def test_apply_refuses_stale_or_invalid_target(publishing, reason):
    p = publishing
    if reason == "draft":
        p.version.published_at = None
    elif reason == "version_changed":
        p.version.version_number = 33
    else:
        p.validation.return_value = ValidationResult([ValidationIssue("test", "error", "invalid")])
    with pytest.raises(RepairError):
        await repair_workflow(p.session, **p.args, apply=True)
    p.update.assert_not_awaited()
    p.publish.assert_not_awaited()


async def test_repeated_apply_does_not_create_another_version(publishing):
    p = publishing
    p.version.graph = repair_graph(p.version.graph)
    report = await repair_workflow(p.session, **p.args, apply=True)
    assert report["result"] == "already repaired"
    p.update.assert_not_awaited()
    p.publish.assert_not_awaited()


async def test_publish_validation_failure_raises_for_transaction_rollback(publishing):
    p = publishing
    p.publish.return_value = (p.workflow, p.version, ValidationResult([
        ValidationIssue("test", "error", "access changed after preflight"),
    ]))
    with pytest.raises(RepairError, match="Publish failed validation"):
        await repair_workflow(p.session, **p.args, apply=True)
