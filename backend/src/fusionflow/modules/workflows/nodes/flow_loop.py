"""`flow.loop` — a container node type: runs its embedded child sub-graph
(its "loop body") once per item in a resolved list, giving each iteration
an isolated copy of the run's variable context under
`variables["loop"] = {"item": ..., "index": ...}` so no state leaks
between iterations (a real bug class this design closes off from day one
— see `registry.ExecutionContext.run_children`'s docstring for the
isolation contract).

`can_contain_children = True`, `child_role = "loop_body"` — the graph-level
half of "nodes can embed other nodes" lives in `engine/graph.py`'s
`parent_id`/`children_of`/`child_roots`; this is the execution-semantics
half.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.run_loop import ChildExecutionError
from fusionflow.modules.workflows.engine.templating import resolve_template_value

logger = logging.getLogger(__name__)


class LoopConfig(BaseModel):
    items_path: str = Field(
        min_length=1,
        description=(
            "Resolves to the list to iterate, e.g. '{{trigger.line_items}}'. "
            "A non-list resolved value iterates zero times."
        ),
        json_schema_extra={"format": "auto_ref", "ref_suffix": "recipients"},
    )
    max_iterations: int = Field(
        default=200,
        ge=1,
        description=(
            "Local safety cap on this loop, independent of (and in addition to) the run's "
            "global loop guard. Extra items beyond this cap are skipped, not an error."
        ),
    )
    continue_on_error: bool = Field(
        default=False,
        description=(
            "When true, a failing iteration is logged and skipped instead of failing the "
            "whole run - for a bulk send where one bad recipient (e.g. an Instagram DM "
            "outside the 24h messaging window) must not abort every recipient after it. "
            "Default false preserves every existing loop's fail-fast behavior."
        ),
    )


class LoopExecutor(NodeExecutor):
    node_type = "flow.loop"
    kind = "action"
    category = "Flow Control"
    label = "Loop"
    description = (
        "Runs its embedded steps once per item in a list, with an isolated variable scope "
        "per iteration."
    )
    config_model = LoopConfig
    can_contain_children = True
    child_role = "loop_body"

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = LoopConfig.model_validate(context.config)
        assert context.graph is not None and context.run_children is not None  # can_contain_children contract

        raw_items = resolve_template_value(config.items_path, context.variables)
        items: list[Any] = raw_items if isinstance(raw_items, list) else []
        truncated = len(items) > config.max_iterations
        items = items[: config.max_iterations]

        child_ids = {c.id for c in context.graph.children_of(context.node_id)}
        root_ids = [n.id for n in context.graph.child_roots(context.node_id)]

        results: list[dict[str, Any]] = []
        for index, item in enumerate(items):
            scoped_variables = dict(context.variables)
            scoped_variables["loop"] = {"item": item, "index": index}
            try:
                await context.run_children(root_ids, scoped_variables, child_ids)
            except ChildExecutionError as exc:
                if not config.continue_on_error:
                    return Failure(f"loop iteration {index} failed: {exc.reason}")
                logger.warning(
                    "loop iteration %s failed (continue_on_error=true, skipping): %s", index, exc.reason
                )
                continue
            results.append({cid: scoped_variables[cid] for cid in child_ids if cid in scoped_variables})

        return Success(output={"results": results, "truncated": truncated, "count": len(results)})


node_executor_registry.register(LoopExecutor())
