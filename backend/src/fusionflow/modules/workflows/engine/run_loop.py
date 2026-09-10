"""The execution engine — walks a workflow graph from its trigger node(s),
executing the matching `NodeExecutor` for each node in turn and recording
one `WorkflowRunStep` per node.

Scheduling (when a run gets started at all) happens elsewhere: the
`simulate` route calls `execute_run` synchronously for an immediate dry
run, and `outbox_poller.py` calls it from a `JobQueue`-dispatched job for
inbox-driven runs. This module itself never touches asyncio directly for
scheduling (no `create_task`) — it is a plain sequence of awaited calls on
whatever session it is handed, matching the plan's "written only against
the JobQueue interface" rule for anything scheduling-adjacent. (`asyncio.
sleep` for retry backoff is the one exception — that's in-run pacing, not
scheduling.)

Container node types (Loop/TryCatch/Parallel — `NodeExecutor.
can_contain_children = True`) execute their embedded child sub-graph by
calling back into this module's own per-node execution machinery via
`ExecutionContext.run_children` (see `_execute_single_node`/`_run_frontier`
below and `registry.ExecutionContext`'s docstring) — a container's
children get real `WorkflowRunStep` rows, real retry, and count against
the same global `loop_guard_count` ceiling as any top-level node, they are
simply scoped to a copy of the variable context and to the container's own
`children_of`/`child_roots` (see `engine/graph.py`).
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.workflows.engine.graph import GraphNode, WorkflowGraph
from fusionflow.modules.workflows.engine.registry import (
    Branch,
    ExecutionContext,
    Failure,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.models import RunStatus, StepStatus, WorkflowRun, WorkflowRunStep

logger = logging.getLogger(__name__)

# Deliberately not read from `fusionflow.config.Settings` — this module
# stays self-contained inside modules/workflows/ per this agent's task
# scope (main.py/config.py are owned elsewhere). Whoever wires the outbox
# poller into app startup should consider promoting this to a proper
# `Settings.WORKFLOW_LOOP_GUARD_MAX` field; until then the env var still
# works because pydantic-settings and `os.environ` read the same process
# environment.
WORKFLOW_LOOP_GUARD_MAX = int(os.environ.get("WORKFLOW_LOOP_GUARD_MAX", "500"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _retry_backoff_seconds(attempt: int) -> float:
    """Exponential backoff with jitter, capped — `attempt` is the attempt
    number that just failed (1-based). Small and bounded on purpose: a
    node retry is meant to ride out a sub-second-to-few-second transient
    blip, not to turn the run loop into a long-running scheduler."""
    return min(2 ** (attempt - 1), 8) + random.uniform(0, 0.25)


class RunLoopError(Exception):
    """Engine-internal problem the run can never recover from on its own
    (no trigger node found; a `NodeResult` subtype that isn't one of the
    three known ones) — distinct from `ChildExecutionError`, which is a
    normal, per-node failure the run loop always knows how to turn into a
    failed run (or, inside a container, potentially recover from)."""


class ChildExecutionError(Exception):
    """A node — top-level or embedded inside a container — failed: its
    executor raised after exhausting retries, or it returned a `Failure`
    NodeResult. Raised by `_execute_single_node`/`_run_frontier`.

    `execute_run` (top level) always catches this and force-fails the run
    — today's exact behavior. A container catches it only if its own
    semantics call for recovery (`flow_try_catch.py`'s wired "error"
    handle); every other container, and Try/Catch with no "error" handle
    wired, simply lets it propagate, which composes correctly through any
    nesting depth since each level's `_execute_single_node` re-raises it
    unchanged after finalizing that level's own step row.
    """

    def __init__(self, node_id: str, reason: str) -> None:
        self.node_id = node_id
        self.reason = reason
        super().__init__(f"node {node_id} failed: {reason}")


class LoopGuardExceeded(Exception):
    """The run's global step ceiling (`WORKFLOW_LOOP_GUARD_MAX`) was hit.

    Deliberately a *different* exception type than `ChildExecutionError`
    so no container — not even Try/Catch — can ever catch and suppress
    it: a runaway loop must always force-fail the whole run, never be
    silently absorbed as a per-branch/per-iteration error.
    """


async def execute_run(
    session: AsyncSession,
    run: WorkflowRun,
    graph: WorkflowGraph,
    *,
    trigger_payload: dict[str, Any] | None = None,
) -> WorkflowRun:
    """Execute `run` to completion (or failure) against `graph`.

    `session` must already be tenant-scoped (`SET LOCAL` applied) for
    `run.tenant_id` — callers are responsible for that, same as every
    other tenant-scoped operation in this codebase. Does not commit; the
    caller (a route handler, a poller job) owns the transaction boundary.

    Raises `RunLoopError` only for a graph that cannot be executed at all
    (no trigger node found); anything that goes wrong *during* execution
    (an unknown node type, a node raising, a `Failure` result, the loop
    guard tripping) instead force-fails `run` in place and returns it
    normally, so a bad workflow never crashes the caller.
    """
    variables: dict[str, Any] = {"trigger": dict(trigger_payload or {})}

    trigger_nodes = graph.trigger_nodes()
    if not trigger_nodes:
        raise RunLoopError("workflow graph has no trigger node")

    try:
        await _run_frontier(session, run, graph, [node.id for node in trigger_nodes], variables)
    except (ChildExecutionError, LoopGuardExceeded) as exc:
        await _fail_run(run, str(exc))
        return run

    run.status = RunStatus.COMPLETED
    run.completed_at = _now()
    return run


async def _run_frontier(
    session: AsyncSession,
    run: WorkflowRun,
    graph: WorkflowGraph,
    start_node_ids: list[str],
    variables: dict[str, Any],
    *,
    allowed_ids: set[str] | None = None,
) -> None:
    """Executes the graph starting from `start_node_ids`, following
    Success/matched-Branch edges until the frontier is exhausted. Mutates
    `variables` in place (each executed node's output lands under
    `variables[node.id]`) — the caller already owns `variables` and can
    read whatever it needs from it afterward, so this returns nothing.

    Raises `ChildExecutionError` (a node failed) or `LoopGuardExceeded`
    (the run-level safety ceiling was hit) instead of returning a status —
    every caller (`execute_run` at the top level, a container's own
    `execute()` via `ExecutionContext.run_children`) already needs a
    try/except around this to decide what "a child failed" means for it.

    `allowed_ids`, when given, restricts both which nodes get executed and
    which edges get followed to that set — used to scope one container's
    execution to its own `children_of`/`child_roots` (`engine/graph.py`)
    so a stray edge into or out of the container can never be silently
    followed at runtime even if it somehow made it past publish-time
    validation's containment-validity rule.
    """
    frontier: list[str] = list(start_node_ids)

    while frontier:
        node_id = frontier.pop(0)
        if allowed_ids is not None and node_id not in allowed_ids:
            continue
        node = graph.node_by_id(node_id)
        if node is None:
            continue

        result = await _execute_single_node(session, run, graph, node, variables)

        if isinstance(result, Branch):
            selected = set(result.selected_edge_handles)
            next_edges = [
                e for e in graph.outgoing_edges(node.id) if (e.source_handle or "default") in selected
            ]
        else:  # Success — _execute_single_node never returns Failure (it raises instead)
            next_edges = graph.outgoing_edges(node.id)

        if allowed_ids is not None:
            next_edges = [e for e in next_edges if e.target in allowed_ids]

        frontier.extend(edge.target for edge in next_edges)


async def _execute_single_node(
    session: AsyncSession,
    run: WorkflowRun,
    graph: WorkflowGraph,
    node: GraphNode,
    variables: dict[str, Any],
) -> NodeResult:
    """Executes exactly one node: records its `WorkflowRunStep`, applies
    opt-in retry-with-backoff, and returns its `NodeResult` (only `Success`
    or `Branch` — a `Failure` result or an exhausted-retries exception is
    always translated into a raised `ChildExecutionError` here, so callers
    never have to check for `Failure` themselves)."""
    executor = node_executor_registry.get(node.data.node_type)
    if executor is None:
        raise ChildExecutionError(node.id, f"no executor registered for node type {node.data.node_type!r}")

    run.loop_guard_count += 1
    if run.loop_guard_count > WORKFLOW_LOOP_GUARD_MAX:
        raise LoopGuardExceeded(
            f"loop guard exceeded ({WORKFLOW_LOOP_GUARD_MAX} steps) — likely unsafe loop"
        )

    step = WorkflowRunStep(
        id=uuid.uuid4(),
        tenant_id=run.tenant_id,
        workflow_run_id=run.id,
        node_id=node.id,
        node_type=node.data.node_type,
        status=StepStatus.RUNNING,
        input={"config": node.data.config, "variables": dict(variables)},
        started_at=_now(),
        attempt=1,
    )
    session.add(step)
    await session.flush()

    is_container = executor.can_contain_children

    async def _run_children(
        start_ids: list[str], scoped_variables: dict[str, Any], allowed_child_ids: set[str]
    ) -> None:
        await _run_frontier(session, run, graph, start_ids, scoped_variables, allowed_ids=allowed_child_ids)

    context = ExecutionContext(
        session=session,
        tenant_id=run.tenant_id,
        run_id=run.id,
        node_id=node.id,
        config=node.data.config,
        variables=variables,
        graph=graph if is_container else None,
        run_children=_run_children if is_container else None,
    )

    max_attempts = 1 + (executor.max_retries if executor.retryable else 0)
    result: NodeResult | None = None
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        step.attempt = attempt
        try:
            result = await executor.execute(context)
            last_exc = None
            break
        except (ChildExecutionError, LoopGuardExceeded) as exc:
            # A container's own internal child failure/loop-guard trip is
            # never retried at the container's own level — retrying would
            # re-run already-recorded, already-committed child steps.
            # Finalize this node's own step, then propagate unchanged.
            step.status = StepStatus.FAILED
            step.error = str(exc)
            step.completed_at = _now()
            raise
        except Exception as exc:  # noqa: BLE001 - a node bug must not crash the run loop
            last_exc = exc
            if attempt < max_attempts:
                logger.warning(
                    "workflow node %s (%s) raised on attempt %d/%d, retrying: %s",
                    node.id,
                    node.data.node_type,
                    attempt,
                    max_attempts,
                    exc,
                )
                await asyncio.sleep(_retry_backoff_seconds(attempt))

    step.completed_at = _now()

    if last_exc is not None:
        logger.exception(
            "workflow node %s (%s) raised after %d attempt(s)",
            node.id,
            node.data.node_type,
            max_attempts,
            exc_info=last_exc,
        )
        step.status = StepStatus.FAILED
        step.error = str(last_exc)
        raise ChildExecutionError(node.id, f"raised after {max_attempts} attempt(s): {last_exc}")

    if isinstance(result, Success):
        step.status = StepStatus.SUCCEEDED
        step.output = result.output
        variables[node.id] = result.output
        return result
    elif isinstance(result, Branch):
        step.status = StepStatus.SUCCEEDED
        step.output = result.output
        variables[node.id] = result.output
        return result
    elif isinstance(result, Failure):
        step.status = StepStatus.FAILED
        step.error = result.error
        raise ChildExecutionError(node.id, result.error)
    else:  # pragma: no cover - exhaustiveness guard
        raise RunLoopError(f"unknown NodeResult type: {result!r}")


async def _fail_run(run: WorkflowRun, reason: str) -> None:
    run.status = RunStatus.FAILED
    run.completed_at = _now()
    logger.warning("workflow run %s failed: %s", run.id, reason)
