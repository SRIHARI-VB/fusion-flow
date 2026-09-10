"""`flow.parallel` — a container node type: conceptually runs each of its
embedded branch chains independently and merges their outputs into
`{"branches": {<branch_root_id>: {...}, ...}}`.

Execution note — a deliberate, documented tradeoff: every node executor in
one run shares a single `AsyncSession` (the engine's one-transaction-per-
run model — see `run_loop.py`'s module docstring), and SQLAlchemy's
`AsyncSession` is not safe for concurrent use from multiple coroutines.
Genuine `asyncio.gather`-style concurrency would need a separate session
(and therefore a separate transaction) per branch, which conflicts with
this run's single-transaction guarantee and is deferred rather than
shipped half-safe. Branches here therefore run *sequentially*, one to
completion before the next starts — correct and stable, just not
concurrent yet. The config/output contract (`wait_for`, `{"branches":
{...}}`) is written so a future per-branch-session implementation would
only change this file's internals, not the graph/config shape anything
else depends on.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.run_loop import ChildExecutionError


class ParallelConfig(BaseModel):
    wait_for: Literal["all", "first"] = "all"


class ParallelExecutor(NodeExecutor):
    node_type = "flow.parallel"
    kind = "action"
    category = "Flow Control"
    label = "Parallel"
    description = (
        "Runs each embedded branch independently and merges their outputs. "
        '"all" waits for every branch; "first" stops once one branch succeeds.'
    )
    config_model = ParallelConfig
    can_contain_children = True
    child_role = "parallel_branch"

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ParallelConfig.model_validate(context.config)
        assert context.graph is not None and context.run_children is not None

        child_ids = {c.id for c in context.graph.children_of(context.node_id)}
        roots = context.graph.child_roots(context.node_id)

        branches: dict[str, Any] = {}
        for root in roots:
            scoped_variables = dict(context.variables)
            try:
                await context.run_children([root.id], scoped_variables, child_ids)
                branches[root.id] = {
                    "status": "succeeded",
                    "output": {cid: scoped_variables[cid] for cid in child_ids if cid in scoped_variables},
                }
            except ChildExecutionError as exc:
                branches[root.id] = {"status": "failed", "error": exc.reason, "failed_node_id": exc.node_id}

            if config.wait_for == "first" and branches[root.id]["status"] == "succeeded":
                break

        return Success(output={"branches": branches})


node_executor_registry.register(ParallelExecutor())
