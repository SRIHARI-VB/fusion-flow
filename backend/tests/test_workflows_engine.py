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
from fusionflow.modules.workflows.engine.run_loop import RunLoopError, execute_run, resume_run
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


def _node(node_id: str, node_type: str, config: dict | None = None, parent_id: str | None = None) -> dict:
    node = {"id": node_id, "type": node_type, "data": {"nodeType": node_type, "config": config or {}}}
    if parent_id is not None:
        node["parentId"] = parent_id
    return node


def _edge(
    edge_id: str,
    source: str,
    target: str,
    source_handle: str | None = None,
    filter_: dict | None = None,
) -> dict:
    edge = {"id": edge_id, "source": source, "target": target}
    if source_handle is not None:
        edge["sourceHandle"] = source_handle
    if filter_ is not None:
        edge["data"] = {"filter": filter_}
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
# Containers: flow.loop / flow.try_catch / flow.parallel
# --------------------------------------------------------------------------


async def test_loop_container_iterates_once_per_item_with_isolated_scope() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("loop", "flow.loop", {"items_path": "{{trigger.items}}"}),
                _node("body", "log.noop", parent_id="loop"),
            ],
            "edges": [_edge("e1", "trigger", "loop")],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={"items": ["a", "b", "c"]})

    assert result.status == RunStatus.COMPLETED
    loop_step = next(s for s in session.added if s.node_id == "loop")
    assert loop_step.output["count"] == 3
    assert loop_step.output["truncated"] is False
    # Each iteration's body step recorded its own loop-scoped context, and
    # they never leak into each other (isolated copy per iteration).
    body_steps = [s for s in session.added if s.node_id == "body"]
    assert len(body_steps) == 3
    assert [s.output["context"]["loop"]["item"] for s in body_steps] == ["a", "b", "c"]
    assert [s.output["context"]["loop"]["index"] for s in body_steps] == [0, 1, 2]
    # The container is a black box from outside: its own recorded output
    # is the only trace of the loop body visible to the rest of the graph.
    assert loop_step.output["results"] == [
        {"body": body_steps[0].output},
        {"body": body_steps[1].output},
        {"body": body_steps[2].output},
    ]


async def test_loop_container_max_iterations_caps_and_marks_truncated() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("loop", "flow.loop", {"items_path": "{{trigger.items}}", "max_iterations": 2}),
                _node("body", "log.noop", parent_id="loop"),
            ],
            "edges": [_edge("e1", "trigger", "loop")],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={"items": ["a", "b", "c", "d"]})

    assert result.status == RunStatus.COMPLETED
    loop_step = next(s for s in session.added if s.node_id == "loop")
    assert loop_step.output["count"] == 2
    assert loop_step.output["truncated"] is True
    assert len([s for s in session.added if s.node_id == "body"]) == 2


async def test_loop_container_child_failure_fails_the_loop_node() -> None:
    from fusionflow.modules.workflows.engine.registry import (
        ExecutionContext,
        Failure,
        NodeExecutor,
        Success,
    )

    class _FailsOnSecondItem(NodeExecutor):
        node_type = "test.fails_on_second_item"
        kind = "action"

        async def execute(self, context: ExecutionContext) -> NodeResult:
            if context.variables["loop"]["index"] == 1:
                return Failure("boom on item 2")
            return Success()

    node_executor_registry.register(_FailsOnSecondItem())
    try:
        graph = WorkflowGraph.from_json(
            {
                "nodes": [
                    _node("trigger", "manual.test_trigger"),
                    _node("loop", "flow.loop", {"items_path": "{{trigger.items}}"}),
                    _node("body", "test.fails_on_second_item", parent_id="loop"),
                ],
                "edges": [_edge("e1", "trigger", "loop")],
            }
        )
        run = _run()
        session = FakeSession()

        result = await execute_run(session, run, graph, trigger_payload={"items": ["a", "b"]})

        assert result.status == RunStatus.FAILED
        loop_step = next(s for s in session.added if s.node_id == "loop")
        assert loop_step.status == StepStatus.FAILED
        assert "iteration 1 failed" in loop_step.error
    finally:
        del node_executor_registry._executors["test.fails_on_second_item"]


async def test_try_catch_routes_to_error_handle_when_wired() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("guard", "flow.try_catch"),
                _node("body", "does.not_exist", parent_id="guard"),
                _node("on_error", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "guard"),
                _edge("e2", "guard", "on_error", source_handle="error"),
            ],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={})

    assert result.status == RunStatus.COMPLETED
    guard_step = next(s for s in session.added if s.node_id == "guard")
    assert guard_step.status == StepStatus.SUCCEEDED
    assert "error" in guard_step.output
    assert [s.node_id for s in session.added] == ["trigger", "guard", "on_error"]


async def test_try_catch_without_error_handle_propagates_failure() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("guard", "flow.try_catch"),
                _node("body", "does.not_exist", parent_id="guard"),
            ],
            "edges": [_edge("e1", "trigger", "guard")],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={})

    assert result.status == RunStatus.FAILED
    guard_step = next(s for s in session.added if s.node_id == "guard")
    assert guard_step.status == StepStatus.FAILED


async def test_try_catch_success_handle_when_wired() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("guard", "flow.try_catch"),
                _node("body", "log.noop", parent_id="guard"),
                _node("after", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "guard"),
                _edge("e2", "guard", "after", source_handle="success"),
            ],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={})

    assert result.status == RunStatus.COMPLETED
    assert [s.node_id for s in session.added] == ["trigger", "guard", "body", "after"]


async def test_try_catch_success_never_follows_the_error_edge_when_only_error_is_wired() -> None:
    """Regression test for a real bug found during design review: when
    only "error" is wired (not "success") and the try body succeeds,
    TryCatch must NOT return a plain `Success` - `_run_frontier` follows
    every outgoing edge of a Success result regardless of handle label,
    which would incorrectly also walk the "error"-labeled edge on a
    success. The fix makes the success path an explicit Branch (selecting
    nothing, since "success" isn't wired) whenever any handle is wired at
    all - see flow_try_catch.py's comment."""
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("guard", "flow.try_catch"),
                _node("body", "log.noop", parent_id="guard"),
                _node("on_error", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "guard"),
                _edge("e2", "guard", "on_error", source_handle="error"),
            ],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={})

    assert result.status == RunStatus.COMPLETED
    assert [s.node_id for s in session.added] == ["trigger", "guard", "body"]
    assert "on_error" not in [s.node_id for s in session.added]


async def test_parallel_runs_each_branch_and_merges_outputs() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("par", "flow.parallel"),
                _node("branch_a", "log.noop", {"message": "a"}, parent_id="par"),
                _node("branch_b", "log.noop", {"message": "b"}, parent_id="par"),
            ],
            "edges": [_edge("e1", "trigger", "par")],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={})

    assert result.status == RunStatus.COMPLETED
    par_step = next(s for s in session.added if s.node_id == "par")
    assert set(par_step.output["branches"].keys()) == {"branch_a", "branch_b"}
    assert par_step.output["branches"]["branch_a"]["status"] == "succeeded"
    assert par_step.output["branches"]["branch_b"]["status"] == "succeeded"


async def test_parallel_branch_failure_is_isolated_from_the_other_branch() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("par", "flow.parallel"),
                _node("branch_a", "does.not_exist", parent_id="par"),
                _node("branch_b", "log.noop", parent_id="par"),
            ],
            "edges": [_edge("e1", "trigger", "par")],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={})

    assert result.status == RunStatus.COMPLETED
    par_step = next(s for s in session.added if s.node_id == "par")
    assert par_step.output["branches"]["branch_a"]["status"] == "failed"
    assert par_step.output["branches"]["branch_b"]["status"] == "succeeded"


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


# --------------------------------------------------------------------------
# validation.validate_for_publish — containers (rules 6 & 7, reachability)
# --------------------------------------------------------------------------


async def test_valid_container_graph_has_no_errors() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("loop", "flow.loop", {"items_path": "{{trigger.items}}"}),
                _node("body", "log.noop", parent_id="loop"),
            ],
            "edges": [_edge("e1", "trigger", "loop")],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert not result.has_errors, result.to_json()


async def test_child_reachable_via_container_child_roots_is_not_flagged_unreachable() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("loop", "flow.loop", {"items_path": "{{trigger.items}}"}),
                _node("body", "log.noop", parent_id="loop"),
            ],
            "edges": [_edge("e1", "trigger", "loop")],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert not any(i.rule == "unreachable_nodes" and i.node_id == "body" for i in result.issues)


async def test_containment_parent_must_be_a_container_node_type() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("not_a_container", "log.noop"),
                _node("body", "log.noop", parent_id="not_a_container"),
            ],
            "edges": [_edge("e1", "trigger", "not_a_container")],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert any(
        i.rule == "containment_validity" and i.node_id == "body" and "cannot contain" in i.message
        for i in result.issues
    )


async def test_containment_missing_parent_is_a_hard_error() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("body", "log.noop", parent_id="ghost"),
            ],
            "edges": [_edge("e1", "trigger", "body")],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert any(
        i.rule == "containment_validity" and i.node_id == "body" and "does not exist" in i.message
        for i in result.issues
    )


async def test_edge_crossing_a_container_boundary_is_a_hard_error() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("loop", "flow.loop", {"items_path": "{{trigger.items}}"}),
                _node("body", "log.noop", parent_id="loop"),
                _node("outsider", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "loop"),
                _edge("e2", "body", "outsider"),  # child -> top-level sibling: not allowed
            ],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert any(i.rule == "containment_validity" and "crosses a container boundary" in i.message for i in result.issues)


async def test_cycle_fully_inside_a_loop_container_is_auto_safe() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("loop", "flow.loop", {"items_path": "{{trigger.items}}"}),
                _node("a", "log.noop", parent_id="loop"),
                _node("b", "log.noop", parent_id="loop"),
            ],
            "edges": [
                _edge("e1", "trigger", "loop"),
                _edge("e2", "a", "b"),
                _edge("e3", "b", "a"),  # cycle a <-> b, both children of the same Loop
            ],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert not any(i.rule == "unsafe_loops" for i in result.issues)


async def test_cycle_spanning_outside_a_loop_container_still_needs_a_loop_safe_node() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("a", "log.noop"),
                _node("b", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "a"),
                _edge("e2", "a", "b"),
                _edge("e3", "b", "a"),  # top-level cycle, no container involved at all
            ],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert any(i.rule == "unsafe_loops" for i in result.issues)


async def test_try_catch_optional_handles_may_be_left_entirely_unwired() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("guard", "flow.try_catch"),
                _node("body", "log.noop", parent_id="guard"),
            ],
            "edges": [_edge("e1", "trigger", "guard")],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert not any(i.rule == "invalid_branches" for i in result.issues)


async def test_try_catch_optional_handle_wired_twice_is_a_hard_error() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("guard", "flow.try_catch"),
                _node("body", "log.noop", parent_id="guard"),
                _node("err1", "log.noop"),
                _node("err2", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "guard"),
                _edge("e2", "guard", "err1", source_handle="error"),
                _edge("e3", "guard", "err2", source_handle="error"),
            ],
        }
    )
    result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
    assert any(i.rule == "invalid_branches" and "expected at most one" in i.message for i in result.issues)


# --------------------------------------------------------------------------
# run_loop — configurable edges (EdgeFilter)
# --------------------------------------------------------------------------


async def test_edge_filter_skips_the_edge_when_it_does_not_match() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("gated", "log.noop"),
            ],
            "edges": [
                _edge(
                    "e1",
                    "trigger",
                    "gated",
                    filter_={"field_path": "trigger.amount", "operator": "gt", "value": 100},
                )
            ],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={"amount": 5})

    assert result.status == RunStatus.COMPLETED
    assert [s.node_id for s in session.added] == ["trigger"]  # "gated" never ran


async def test_edge_filter_follows_the_edge_when_it_matches() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("gated", "log.noop"),
            ],
            "edges": [
                _edge(
                    "e1",
                    "trigger",
                    "gated",
                    filter_={"field_path": "trigger.amount", "operator": "gt", "value": 100},
                )
            ],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={"amount": 500})

    assert result.status == RunStatus.COMPLETED
    assert [s.node_id for s in session.added] == ["trigger", "gated"]


# --------------------------------------------------------------------------
# run_loop — Suspend / RunSuspended / resume_run (Phase 8 Part A)
# --------------------------------------------------------------------------


def _make_ask_executor(node_type: str):
    """Builds a throwaway `can_suspend` test node type - a real
    `NodeExecutor` subclass, constructed fresh per test/node_type so tests
    registering the same type name never collide across test runs."""
    from fusionflow.modules.workflows.engine.registry import ExecutionContext, NodeExecutor, NodeResult, Suspend

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Suspend(correlation_key=context.variables["trigger"]["from"])

    async def extract_resume_value(self, config: dict, resume_payload: dict) -> Any:
        return resume_payload.get("text")

    executor_cls = type(
        "_Executor",
        (NodeExecutor,),
        {
            "node_type": node_type,
            "kind": "action",
            "can_suspend": True,
            "execute": execute,
            "extract_resume_value": extract_resume_value,
        },
    )
    return executor_cls()


def _ask_graph(connector_instance_id: uuid.UUID | None = None) -> WorkflowGraph:
    ask_config = {"connector_instance_id": str(connector_instance_id)} if connector_instance_id else {}
    return WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node("ask", "test.ask_question", ask_config),
                _node("after", "log.noop", {"message": "after"}),
            ],
            "edges": [
                _edge("e1", "trigger", "ask"),
                _edge("e2", "ask", "after"),
            ],
        }
    )


async def test_ask_node_suspends_and_persists_waiting_state() -> None:
    node_executor_registry.register(_make_ask_executor("test.ask_question"))
    try:
        connector_id = uuid.uuid4()
        graph = _ask_graph(connector_id)
        run = _run()
        session = FakeSession()

        result = await execute_run(session, run, graph, trigger_payload={"from": "15551234567"})

        assert result.status == RunStatus.WAITING
        assert result.waiting_node_id == "ask"
        assert result.waiting_correlation_key == "15551234567"
        assert result.waiting_connector_instance_id == connector_id
        assert result.waiting_frontier == ["after"]
        assert result.waiting_variables["trigger"] == {"from": "15551234567"}
        assert result.waiting_variables["ask"] == {"asked": True}
        assert result.waiting_expires_at is not None
        # "after" never ran - the run paused right after "ask" executed.
        assert [s.node_id for s in session.added] == ["trigger", "ask"]
        ask_step = next(s for s in session.added if s.node_id == "ask")
        assert ask_step.status == StepStatus.SUCCEEDED
        assert ask_step.output == {"asked": True}
    finally:
        del node_executor_registry._executors["test.ask_question"]


async def test_resume_run_continues_from_exact_frontier_with_reply_merged() -> None:
    node_executor_registry.register(_make_ask_executor("test.ask_question"))
    try:
        graph = _ask_graph()
        run = _run()
        session = FakeSession()
        suspended = await execute_run(session, run, graph, trigger_payload={"from": "15551234567"})
        assert suspended.status == RunStatus.WAITING

        resumed = await resume_run(session, run, graph, reply_payload={"text": "Large"})

        assert resumed.status == RunStatus.COMPLETED
        assert resumed.waiting_node_id is None
        assert resumed.waiting_correlation_key is None
        assert resumed.waiting_frontier is None
        assert resumed.waiting_variables is None
        assert resumed.waiting_expires_at is None
        assert [s.node_id for s in session.added] == ["trigger", "ask", "after"]
        after_step = next(s for s in session.added if s.node_id == "after")
        assert after_step.output["context"]["ask"] == {"reply": "Large"}
        assert after_step.output["context"]["trigger"] == {"from": "15551234567"}
    finally:
        del node_executor_registry._executors["test.ask_question"]


async def test_a_second_suspend_further_down_the_resumed_chain_also_works() -> None:
    node_executor_registry.register(_make_ask_executor("test.ask_question"))
    try:
        graph = WorkflowGraph.from_json(
            {
                "nodes": [
                    _node("trigger", "manual.test_trigger"),
                    _node("ask1", "test.ask_question"),
                    _node("ask2", "test.ask_question"),
                    _node("after", "log.noop"),
                ],
                "edges": [
                    _edge("e1", "trigger", "ask1"),
                    _edge("e2", "ask1", "ask2"),
                    _edge("e3", "ask2", "after"),
                ],
            }
        )
        run = _run()
        session = FakeSession()

        first = await execute_run(session, run, graph, trigger_payload={"from": "15551234567"})
        assert first.status == RunStatus.WAITING
        assert first.waiting_node_id == "ask1"
        assert first.waiting_frontier == ["ask2"]

        second = await resume_run(session, run, graph, reply_payload={"text": "Large"})
        assert second.status == RunStatus.WAITING
        assert second.waiting_node_id == "ask2"
        assert second.waiting_frontier == ["after"]
        assert second.waiting_variables["ask1"] == {"reply": "Large"}

        third = await resume_run(session, run, graph, reply_payload={"text": "Blue"})
        assert third.status == RunStatus.COMPLETED
        after_step = next(s for s in session.added if s.node_id == "after")
        assert after_step.output["context"]["ask1"] == {"reply": "Large"}
        assert after_step.output["context"]["ask2"] == {"reply": "Blue"}
    finally:
        del node_executor_registry._executors["test.ask_question"]


async def test_suspend_node_inside_a_container_is_a_hard_error() -> None:
    node_executor_registry.register(_make_ask_executor("test.suspend_node"))
    try:
        graph = WorkflowGraph.from_json(
            {
                "nodes": [
                    _node("trigger", "manual.test_trigger"),
                    _node("loop", "flow.loop", {"items_path": "{{trigger.items}}"}),
                    _node("ask", "test.suspend_node", parent_id="loop"),
                ],
                "edges": [_edge("e1", "trigger", "loop")],
            }
        )
        result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
        assert any(
            i.rule == "suspend_not_in_container" and i.node_id == "ask" for i in result.issues
        )
    finally:
        del node_executor_registry._executors["test.suspend_node"]


async def test_suspend_node_at_top_level_is_allowed() -> None:
    node_executor_registry.register(_make_ask_executor("test.suspend_node"))
    try:
        graph = WorkflowGraph.from_json(
            {
                "nodes": [
                    _node("trigger", "manual.test_trigger"),
                    _node("ask", "test.suspend_node"),
                ],
                "edges": [_edge("e1", "trigger", "ask")],
            }
        )
        result = await validation.validate_for_publish(FakeSession(), tenant_id=uuid.uuid4(), graph=graph)
        assert not any(i.rule == "suspend_not_in_container" for i in result.issues)
    finally:
        del node_executor_registry._executors["test.suspend_node"]


async def test_edge_filter_applies_in_addition_to_branch_handle_matching() -> None:
    graph = WorkflowGraph.from_json(
        {
            "nodes": [
                _node("trigger", "manual.test_trigger"),
                _node(
                    "cond",
                    "condition.field_compare",
                    {"field_path": "trigger.keyword", "operator": "eq", "value": "refund"},
                ),
                _node("on_true", "log.noop"),
            ],
            "edges": [
                _edge("e1", "trigger", "cond"),
                # Matched handle, but the edge's own filter still fails.
                _edge(
                    "e2",
                    "cond",
                    "on_true",
                    source_handle="true",
                    filter_={"field_path": "trigger.amount", "operator": "gt", "value": 1000},
                ),
            ],
        }
    )
    run = _run()
    session = FakeSession()

    result = await execute_run(session, run, graph, trigger_payload={"keyword": "refund", "amount": 5})

    assert result.status == RunStatus.COMPLETED
    assert [s.node_id for s in session.added] == ["trigger", "cond"]  # "on_true" gated out
