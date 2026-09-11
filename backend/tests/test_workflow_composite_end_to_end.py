"""End-to-end tests for the composable-builder redesign's "ask and branch"
nodes (Phase 4): builds an *authored* graph exactly as a workflow author
would wire it on the canvas (one `whatsapp.ask_choice`/`flow.confirm` node
with per-option edges, no manually-added condition node), compiles it with
`resolve_composite_branches` (the same step `service.publish_workflow`/
`simulate_workflow` runs), and drives it through the real `execute_run`/
`resume_run` engine - proving the whole suspend -> synthesized-branch ->
resume chain actually takes the correct path, not just that the graph
*shape* looks right (that's `test_workflow_composite_branching.py`'s job).

Same "no Postgres required" philosophy as `test_workflows_engine.py`:
`FakeSession` stands in for a real `AsyncSession`, and the WhatsApp
adapter's send calls plus `connector_service.get_instance` are
monkeypatched.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.run_loop import execute_run, resume_run
from fusionflow.modules.workflows.engine.template_resolution import resolve_composite_branches
from fusionflow.modules.workflows.models import RunStatus, WorkflowRun
from fusionflow.modules.workflows.nodes import _whatsapp_common
from fusionflow.modules.workflows.nodes import flow_confirm, whatsapp_ask_choice

pytestmark = pytest.mark.asyncio


class FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def _run() -> WorkflowRun:
    return WorkflowRun(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workflow_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(),
        trigger_event_ref="test",
        status=RunStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
        loop_guard_count=0,
    )


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {"id": node_id, "type": node_type, "data": {"nodeType": node_type, "config": config or {}}}


def _edge(edge_id: str, source: str, target: str, source_handle: str | None = None) -> dict:
    edge = {"id": edge_id, "source": source, "target": target}
    if source_handle is not None:
        edge["sourceHandle"] = source_handle
    return edge


def _fake_connector_instance(tenant_id: uuid.UUID) -> ConnectorInstance:
    return ConnectorInstance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_type_id=uuid.uuid4(),
        state=ConnectorState.CONNECTED,
        display_name="Test WhatsApp",
        provider_ref_ids={"phone_number_id": "stub-phone-1"},
    )


def _mock_whatsapp_sends(monkeypatch: pytest.MonkeyPatch, instance: ConnectorInstance) -> None:
    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance:
        return instance

    async def fake_send_interactive_message(**kwargs) -> None:
        return None

    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(whatsapp_ask_choice.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)
    monkeypatch.setattr(flow_confirm.whatsapp_adapter, "send_interactive_message", fake_send_interactive_message)


async def test_ask_choice_authored_graph_takes_only_the_matching_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    _mock_whatsapp_sends(monkeypatch, instance)

    authored = {
        "nodes": [
            _node("trigger", "manual.test_trigger"),
            _node(
                "ask",
                "whatsapp.ask_choice",
                {
                    "connector_instance_id": str(instance.id),
                    "to": "{{trigger.from}}",
                    "question": "What size?",
                    "source": {
                        "kind": "static",
                        "options": [{"id": "small", "label": "Small"}, {"id": "large", "label": "Large"}],
                    },
                },
            ),
            _node("small_path", "log.noop", {"message": "small"}),
            _node("large_path", "log.noop", {"message": "large"}),
        ],
        "edges": [
            _edge("e1", "trigger", "ask"),
            _edge("e2", "ask", "small_path", source_handle="small"),
            _edge("e3", "ask", "large_path", source_handle="large"),
        ],
    }

    compiled = resolve_composite_branches(authored)
    graph = WorkflowGraph.from_json(compiled)

    run = _run()
    session = FakeSession()
    suspended = await execute_run(session, run, graph, trigger_payload={"from": "15551234567"})
    assert suspended.status == RunStatus.WAITING
    assert suspended.waiting_node_id == "ask"

    resumed = await resume_run(session, run, graph, reply_payload={"interactive": {"id": "large", "title": "Large"}})

    assert resumed.status == RunStatus.COMPLETED
    executed_node_ids = [s.node_id for s in session.added]
    assert "large_path" in executed_node_ids
    assert "small_path" not in executed_node_ids
    large_step = next(s for s in session.added if s.node_id == "large_path")
    assert large_step.output["context"]["ask"] == {"reply": {"id": "large", "label": "Large"}}


async def test_ask_choice_unmatched_reply_falls_through_the_optional_default_handle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Neither branch is taken, and the run still completes cleanly - the
    synthesized `condition.multi_branch`'s `default` handle is optional
    (Part A), so a customer's free-text reply that matches no option
    doesn't crash the run or force an author to wire a "no match" path
    the canvas never exposed a port for."""
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    _mock_whatsapp_sends(monkeypatch, instance)

    authored = {
        "nodes": [
            _node("trigger", "manual.test_trigger"),
            _node(
                "ask",
                "whatsapp.ask_choice",
                {
                    "connector_instance_id": str(instance.id),
                    "to": "{{trigger.from}}",
                    "question": "What size?",
                    "source": {
                        "kind": "static",
                        "options": [{"id": "small", "label": "Small"}, {"id": "large", "label": "Large"}],
                    },
                },
            ),
            _node("small_path", "log.noop"),
            _node("large_path", "log.noop"),
        ],
        "edges": [
            _edge("e1", "trigger", "ask"),
            _edge("e2", "ask", "small_path", source_handle="small"),
            _edge("e3", "ask", "large_path", source_handle="large"),
        ],
    }

    graph = WorkflowGraph.from_json(resolve_composite_branches(authored))
    run = _run()
    session = FakeSession()
    await execute_run(session, run, graph, trigger_payload={"from": "15551234567"})

    resumed = await resume_run(session, run, graph, reply_payload={"text": "I don't understand"})

    assert resumed.status == RunStatus.COMPLETED
    executed_node_ids = [s.node_id for s in session.added]
    assert "small_path" not in executed_node_ids
    assert "large_path" not in executed_node_ids


async def test_flow_confirm_authored_graph_takes_the_yes_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)
    _mock_whatsapp_sends(monkeypatch, instance)

    authored = {
        "nodes": [
            _node("trigger", "manual.test_trigger"),
            _node(
                "confirm",
                "flow.confirm",
                {"connector_instance_id": str(instance.id), "to": "{{trigger.from}}", "question": "Proceed?"},
            ),
            _node("yes_path", "log.noop"),
            _node("no_path", "log.noop"),
        ],
        "edges": [
            _edge("e1", "trigger", "confirm"),
            _edge("e2", "confirm", "yes_path", source_handle="yes"),
            _edge("e3", "confirm", "no_path", source_handle="no"),
        ],
    }

    graph = WorkflowGraph.from_json(resolve_composite_branches(authored))
    run = _run()
    session = FakeSession()
    await execute_run(session, run, graph, trigger_payload={"from": "15551234567"})

    resumed = await resume_run(session, run, graph, reply_payload={"text": "sure"})

    assert resumed.status == RunStatus.COMPLETED
    executed_node_ids = [s.node_id for s in session.added]
    assert "yes_path" in executed_node_ids
    assert "no_path" not in executed_node_ids
