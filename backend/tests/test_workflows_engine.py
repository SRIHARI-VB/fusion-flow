"""Offline unit tests for the workflow engine (plan M5) — no Postgres
required. Exercises the run loop and publish-time validation directly
against constructed graphs, using a minimal fake session (the built-in
node executors never touch `context.session`, so a real DB connection is
never needed for these).

`test_rls_isolation.py`-style live-DB coverage (workflows CRUD through the
FastAPI routes, RLS isolation for the new tables, the outbox poller
against a real Postgres) is explicitly NOT attempted here — this
environment has no Postgres. See this agent's handoff notes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import pytest

from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.registry import node_executor_registry
from fusionflow.modules.workflows.engine.run_loop import RunLoopError, execute_run
from fusionflow.modules.workflows.models import RunStatus, StepStatus, WorkflowRun
from fusionflow.modules.workflows import validation

pytestmark = pytest.mark.asyncio


class FakeSession:
    """Stands in for an `AsyncSession`. `add`/`flush` are no-ops (the
    built-in nodes never issue queries); `get` supports the one
    validation-rule test that needs it."""

    def __init__(self, get_result: Any = None) -> None:
        self.added: list[Any] = []
        self._get_result = get_result

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def get(self, model: Any, ident: Any) -> Any:
        return self._get_result


def _run(workflow_id: uuid.UUID | None = None) -> WorkflowRun:
    return WorkflowRun(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workflow_id=workflow_id or uuid.uuid4(),
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


# --------------------------------------------------------------------------
# run_loop.execute_run
# --------------------------------------------------------------------------


async def test_linear_chain_completes_and_records_every_step() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("noop1", "log.noop", {"message": "first"}),
                _node("noop2", "log.noop", {"message": "second"}),
            ],
            "edges": [
                _edge("e1", "trigger", "noop1"),
                _edge("e2", "noop1", "noop2"),
            ],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={"foo": "bar"})

    assert result.status == RunStatus.COMPLETED
    assert result.loop_guard_count == 3
    assert [s.node_id for s in session.added] == ["trigger", "noop1", "noop2"]
    assert all(s.status == StepStatus.SUCCEEDED for s in session.added)
    # log.noop echoes the running context, including the trigger payload.
    assert session.added[1].output["context"]["trigger"] == {"foo": "bar"}


async def test_condition_branch_only_follows_matched_handle() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node(
                    "cond",
                    "condition.field_compare",
                    {"field_path": "trigger.keyword", "operator": "eq", "value": "refund"},
                ),
                _node("on_true", "log.noop", {"message": "matched"}),
                _node("on_false", "log.noop", {"message": "not matched"}),
            ],
            "edges": [
                _edge("e1", "trigger", "cond"),
                _edge("e2", "cond", "on_true", source_handle="true"),
                _edge("e3", "cond", "on_false", source_handle="false"),
            ],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={"keyword": "refund"})

    assert result.status == RunStatus.COMPLETED
    visited = [s.node_id for s in session.added]
    assert visited == ["trigger", "cond", "on_true"]
    assert "on_false" not in visited


async def test_no_trigger_node_raises_run_loop_error() -> None:
    graph = WorkflowGraph.from_json(
        {"nodes": [_node("noop1", "log.noop")], "edges": []}
    )
    with pytest.raises(RunLoopError, match="no trigger node"):
        await execute_run(FakeSession(), _run(), graph)


async def test_unknown_node_type_fails_the_run_without_raising() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("mystery", "does.not_exist"),
            ],
            "edges": [_edge("e1", "trigger", "mystery")],
        }
    )
    run = _run()
    result = await execute_run(FakeSession(), run, graph)
    assert result.status == RunStatus.FAILED


async def test_retryable_node_recovers_within_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    from fusionflow.modules.workflows.engine import run_loop
    from fusionflow.modules.workflows.engine.registry import ExecutionContext, NodeExecutor, NodeResult, Success

    monkeypatch.setattr(run_loop.asyncio, "sleep", lambda *_a, **_k: _noop_sleep())

    attempts: list[int] = []

    class _FlakyThenSucceeds(NodeExecutor):
        node_type = "test.flaky_then_succeeds"
        kind = "action"
        retryable = True
        max_retries = 2

        async def execute(self, context: ExecutionContext) -> NodeResult:
            attempts.append(1)
            if len(attempts) < 3:
                raise RuntimeError("transient")
            return Success()

    node_executor_registry.register(_FlakyThenSucceeds())
    try:
        graph = WorkflowGraph.from_json(
            {
                "nodes": [_node("trigger", "manual.test_trigger"), _node("flaky", "test.flaky_then_succeeds")],
                "edges": [_edge("e1", "trigger", "flaky")],
            }
        )
        run = _run()
        session = FakeSession()

        result = await execute_run(session, run, graph)

        assert result.status == RunStatus.COMPLETED
        assert len(attempts) == 3
        flaky_step = next(s for s in session.added if s.node_id == "flaky")
        assert flaky_step.attempt == 3
        assert flaky_step.status == StepStatus.SUCCEEDED
    finally:
        del node_executor_registry._executors["test.flaky_then_succeeds"]


async def test_retryable_node_fails_run_after_exhausting_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    from fusionflow.modules.workflows.engine import run_loop
    from fusionflow.modules.workflows.engine.registry import ExecutionContext, NodeExecutor, NodeResult

    monkeypatch.setattr(run_loop.asyncio, "sleep", lambda *_a, **_k: _noop_sleep())

    attempts: list[int] = []

    class _AlwaysFails(NodeExecutor):
        node_type = "test.always_fails"
        kind = "action"
        retryable = True
        max_retries = 2

        async def execute(self, context: ExecutionContext) -> NodeResult:
            attempts.append(1)
            raise RuntimeError("permanently broken")

    node_executor_registry.register(_AlwaysFails())
    try:
        graph = WorkflowGraph.from_json(
            {
                "nodes": [_node("trigger", "manual.test_trigger"), _node("bad", "test.always_fails")],
                "edges": [_edge("e1", "trigger", "bad")],
            }
        )
        run = _run()
        session = FakeSession()

        result = await execute_run(session, run, graph)

        assert result.status == RunStatus.FAILED
        assert len(attempts) == 3  # 1 initial + 2 retries
        bad_step = next(s for s in session.added if s.node_id == "bad")
        assert bad_step.attempt == 3
        assert bad_step.status == StepStatus.FAILED
        assert "permanently broken" in bad_step.error
    finally:
        del node_executor_registry._executors["test.always_fails"]


async def _noop_sleep() -> None:
    return None


async def test_non_retryable_node_fails_immediately_on_first_exception() -> None:
    """Default `retryable = False` - unchanged, backward-compatible
    behavior for every existing node type: one attempt, no backoff."""
    from fusionflow.modules.workflows.engine.registry import ExecutionContext, NodeExecutor, NodeResult

    attempts: list[int] = []

    class _AlwaysFailsNonRetryable(NodeExecutor):
        node_type = "test.always_fails_non_retryable"
        kind = "action"

        async def execute(self, context: ExecutionContext) -> NodeResult:
            attempts.append(1)
            raise RuntimeError("boom")

    node_executor_registry.register(_AlwaysFailsNonRetryable())
    try:
        graph = WorkflowGraph.from_json(
            {
                "nodes": [
                    _node("trigger", "manual.test_trigger"),
                    _node("bad", "test.always_fails_non_retryable"),
                ],
                "edges": [_edge("e1", "trigger", "bad")],
            }
        )
        run = _run()
        session = FakeSession()

        result = await execute_run(session, run, graph)

        assert result.status == RunStatus.FAILED
        assert len(attempts) == 1
        bad_step = next(s for s in session.added if s.node_id == "bad")
        assert bad_step.attempt == 1
    finally:
        del node_executor_registry._executors["test.always_fails_non_retryable"]


async def test_loop_guard_force_fails_runaway_cycles(monkeypatch: pytest.MonkeyPatch) -> None:
    from fusionflow.modules.workflows.engine import run_loop

    monkeypatch.setattr(run_loop, "WORKFLOW_LOOP_GUARD_MAX", 5)

    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("loopy", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "loopy"),
                _edge("e2", "loopy", "loopy"),  # self-loop, no exit condition
            ],
        }
    )
    run = _run()
    result = await run_loop.execute_run(FakeSession(), run, graph)

    assert result.status == RunStatus.FAILED
    assert result.loop_guard_count == 6  # 1 (trigger) + 5 (guard ceiling) then stop


# --------------------------------------------------------------------------
# validation.validate_for_publish
# --------------------------------------------------------------------------


async def test_valid_graph_has_no_errors() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node(
                    "cond",
                    "condition.field_compare",
                    {"field_path": "trigger.keyword", "operator": "eq", "value": "x"},
                ),
                _node("on_true", "log.noop"),
                _node("on_false", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "cond"),
                _edge("e2", "cond", "on_true", source_handle="true"),
                _edge("e3", "cond", "on_false", source_handle="false"),
            ],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert not result.has_errors, result.to_json()


async def test_missing_required_field_is_a_hard_error() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("cond", "condition.field_compare", {}),  # missing required field_path
            ],
            "edges": [_edge("e1", "trigger", "cond")],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert result.has_errors
    assert any(i.rule == "missing_required_fields" for i in result.issues)


async def test_unreachable_node_is_a_hard_error() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("orphan", "log.noop"),
            ],
            "edges": [],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert result.has_errors
    assert any(i.rule == "unreachable_nodes" and i.node_id == "orphan" for i in result.issues)


async def test_unwired_branch_handle_is_a_hard_error() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node(
                    "cond",
                    "condition.field_compare",
                    {"field_path": "trigger.keyword", "operator": "eq", "value": "x"},
                ),
                _node("on_true", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "cond"),
                _edge("e2", "cond", "on_true", source_handle="true"),
                # "false" handle never wired
            ],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert result.has_errors
    assert any(i.rule == "invalid_branches" for i in result.issues)


async def test_unsafe_cycle_is_a_hard_error_unless_loop_safe_node_present() -> None:
    unsafe_graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("a", "log.noop"),
                _node("b", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "a"),
                _edge("e2", "a", "b"),
                _edge("e3", "b", "a"),  # cycle a <-> b
            ],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=unsafe_graph)
    assert any(i.rule == "unsafe_loops" for i in result.issues)


async def test_cycle_with_loop_safe_node_is_allowed() -> None:
    from fusionflow.modules.workflows.engine.registry import ExecutionContext, NodeExecutor, NodeResult, Success

    class _LoopSafeNoop(NodeExecutor):
        node_type = "test.loop_safe_noop"
        kind = "action"
        loop_safety_field = "max_iterations"

        async def execute(self, context: ExecutionContext) -> NodeResult:
            return Success()

    node_executor_registry.register(_LoopSafeNoop())
    try:
        safe_graph = WorkflowGraph.from_json(
            {
                "nodes": [
                    _node("trigger", "manual.test_trigger"),
                    _node("a", "test.loop_safe_noop", {"max_iterations": 10}),
                    _node("b", "log.noop"),
                ],
                "edges": [
                    _edge("e1", "trigger", "a"),
                    _edge("e2", "a", "b"),
                    _edge("e3", "b", "a"),
                ],
            }
        )
        result = await validation.validate_for_publish(
            FakeSession(), tenant_id=uuid.uuid4(), graph=safe_graph
        )
        assert not any(i.rule == "unsafe_loops" for i in result.issues)
    finally:
        del node_executor_registry._executors["test.loop_safe_noop"]


async def test_connector_reference_with_malformed_uuid_is_a_hard_error() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("noop", "log.noop", {"connector_instance_id": "not-a-uuid"}),
            ],
            "edges": [_edge("e1", "trigger", "noop")],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert any(i.rule == "disconnected_connector_reference" and i.severity == "error" for i in result.issues)
