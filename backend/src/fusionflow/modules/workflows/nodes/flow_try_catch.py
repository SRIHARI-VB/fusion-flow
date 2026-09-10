"""`flow.try_catch` — a container node type: runs its embedded child
sub-graph (its "try body") and, if any child fails, either routes to a
wired "error" output handle (catching the failure) or re-raises exactly
like today's fail-fast behavior when no "error" handle is wired. A
Try/Catch with nothing wired to "error" behaves identically to not having
one at all — fully backward compatible, opt-in only.

`output_handles` is deliberately left unset here (both "success" and
"error" go through `optional_output_handles` instead) — see
`registry.NodeExecutor.optional_output_handles`'s docstring for why: an
author may wire zero, one, or both of them, unlike a required
`output_handles` list where every declared handle must be wired exactly
once.
"""

from __future__ import annotations

from pydantic import BaseModel

from fusionflow.modules.workflows.engine.registry import (
    Branch,
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.run_loop import ChildExecutionError


class TryCatchConfig(BaseModel):
    """No config fields today — a plain container. Kept as its own model
    (rather than `config_model = None`) so the builder UI still renders a
    (currently empty) config drawer consistently with every other node."""


class TryCatchExecutor(NodeExecutor):
    node_type = "flow.try_catch"
    kind = "condition"
    category = "Flow Control"
    label = "Try / Catch"
    description = (
        'Runs its embedded steps; if one fails, routes to the wired "error" handle instead of '
        'failing the whole run. With no "error" handle wired, a failure propagates exactly as if '
        "this node weren't there."
    )
    config_model = TryCatchConfig
    optional_output_handles = ["success", "error"]
    can_contain_children = True
    child_role = "try_body"

    async def execute(self, context: ExecutionContext) -> NodeResult:
        assert context.graph is not None and context.run_children is not None

        child_ids = {c.id for c in context.graph.children_of(context.node_id)}
        root_ids = [n.id for n in context.graph.child_roots(context.node_id)]
        scoped_variables = dict(context.variables)

        wired_handles = {
            (edge.source_handle or "default") for edge in context.graph.outgoing_edges(context.node_id)
        }

        try:
            await context.run_children(root_ids, scoped_variables, child_ids)
        except ChildExecutionError as exc:
            if "error" not in wired_handles:
                raise
            return Branch(
                selected_edge_handles=["error"],
                output={"error": exc.reason, "failed_node_id": exc.node_id},
            )

        output = {cid: scoped_variables[cid] for cid in child_ids if cid in scoped_variables}
        if "success" in wired_handles:
            return Branch(selected_edge_handles=["success"], output=output)
        return Success(output=output)


node_executor_registry.register(TryCatchExecutor())
