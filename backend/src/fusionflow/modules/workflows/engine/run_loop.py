"""The execution engine — walks a workflow graph from its trigger node(s),
executing the matching `NodeExecutor` for each node in turn and recording
one `WorkflowRunStep` per node.

Scheduling (when a run gets started at all) happens elsewhere: the
`simulate` route calls `execute_run` synchronously for an immediate dry
run, and `outbox_poller.py` calls it from a `JobQueue`-dispatched job for
inbox-driven runs. This module itself never touches asyncio directly
(no `create_task`/`sleep`) — it is a plain sequence of awaited calls on
whatever session it is handed, matching the plan's "written only against
the JobQueue interface" rule for anything scheduling-adjacent.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.registry import (
    Branch,
    ExecutionContext,
    Failure,
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


class RunLoopError(Exception):
    """Engine-internal problem (missing trigger node, unknown node type
    with no registered executor) — distinct from a `Failure` NodeResult,
    which is a normal, recorded node failure."""


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
    (an unknown node type, a node raising, a `Failure` result) instead
    force-fails `run` in place and returns it normally, so a bad workflow
    never crashes the caller.
    """
    variables: dict[str, Any] = {"trigger": dict(trigger_payload or {})}

    trigger_nodes = graph.trigger_nodes()
    if not trigger_nodes:
        raise RunLoopError("workflow graph has no trigger node")

    # Plain BFS/DFS worklist — order doesn't matter for correctness here
    # since every node's inputs come from `variables`, populated as each
    # node completes, not from queue position.
    frontier: list[str] = [node.id for node in trigger_nodes]

    while frontier:
        node_id = frontier.pop(0)
        node = graph.node_by_id(node_id)
        if node is None:
            continue

        executor = node_executor_registry.get(node.data.node_type)
        if executor is None:
            await _fail_run(run, f"no executor registered for node type {node.data.node_type!r}")
            return run

        run.loop_guard_count += 1
        if run.loop_guard_count > WORKFLOW_LOOP_GUARD_MAX:
            await _fail_run(
                run,
                f"loop guard exceeded ({WORKFLOW_LOOP_GUARD_MAX} steps) — likely unsafe loop",
            )
            return run

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

        context = ExecutionContext(
            session=session,
            tenant_id=run.tenant_id,
            run_id=run.id,
            node_id=node.id,
            config=node.data.config,
            variables=variables,
        )

        try:
            result = await executor.execute(context)
        except Exception as exc:  # noqa: BLE001 - a node bug must not crash the run loop
            logger.exception("workflow node %s (%s) raised", node.id, node.data.node_type)
            step.status = StepStatus.FAILED
            step.error = str(exc)
            step.completed_at = _now()
            await _fail_run(run, f"node {node.id} raised: {exc}")
            return run

        step.completed_at = _now()

        if isinstance(result, Success):
            step.status = StepStatus.SUCCEEDED
            step.output = result.output
            variables[node.id] = result.output
            next_edges = graph.outgoing_edges(node.id)
        elif isinstance(result, Branch):
            step.status = StepStatus.SUCCEEDED
            step.output = result.output
            variables[node.id] = result.output
            selected = set(result.selected_edge_handles)
            next_edges = [
                e for e in graph.outgoing_edges(node.id) if (e.source_handle or "default") in selected
            ]
        elif isinstance(result, Failure):
            step.status = StepStatus.FAILED
            step.error = result.error
            await _fail_run(run, f"node {node.id} failed: {result.error}")
            return run
        else:  # pragma: no cover - exhaustiveness guard
            raise RunLoopError(f"unknown NodeResult type: {result!r}")

        frontier.extend(edge.target for edge in next_edges)

    run.status = RunStatus.COMPLETED
    run.completed_at = _now()
    return run


async def _fail_run(run: WorkflowRun, reason: str) -> None:
    run.status = RunStatus.FAILED
    run.completed_at = _now()
    logger.warning("workflow run %s failed: %s", run.id, reason)
