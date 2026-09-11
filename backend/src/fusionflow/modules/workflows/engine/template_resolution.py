"""Compiles a graph's `WorkflowNodeTemplate`-backed nodes down to their
real, registered `base_node_type` + merged config, so the run loop and
publish-time validation never need to know templates exist at all — see
`modules.admin.models.WorkflowNodeTemplate`'s docstring and
`modules.workflows.nodes.connector_action`'s module docstring for the
full "catalog/config, not code" picture this is one piece of.

Two call sites, both in `service.py`:

* `publish_workflow` compiles once at publish time and persists the
  result onto `WorkflowVersion.compiled_graph` (the immutable artifact
  the engine actually executes — `outbox_poller.py` reads this, not
  `.graph`). `WorkflowVersion.graph` (the *authored* form, still
  referencing template keys) is left untouched, so editing a
  previously-published workflow keeps showing the friendly template
  identity instead of the generic executor it compiles to.
* `simulate_workflow` compiles transiently, in-memory only, on every
  call — a dry run always reflects whichever templates are active right
  now, even before the workflow is ever published.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.workflows.engine.composite_branching import get_composite_branch_source


async def resolve_node_templates(session: AsyncSession, graph_json: dict[str, Any] | None) -> dict[str, Any]:
    """Returns a *new* graph dict with every node whose `data.nodeType`
    matches an active `WorkflowNodeTemplate.key` rewritten to that
    template's `base_node_type`, with `config` = the template's
    `default_config` shallow-merged under the node's own `config` (the
    node instance's own values always win over the template default —
    the same "override, don't replace" precedent this codebase already
    uses for entitlement resolution). A node whose `nodeType` isn't a
    known template key is returned unchanged — this function is a no-op
    for a graph built entirely from raw registered node types.
    """
    if not graph_json:
        return dict(graph_json or {})

    templates = await admin_service.list_workflow_node_templates(session, active_only=True)
    by_key = {t.key: t for t in templates}
    if not by_key:
        return graph_json

    compiled = copy.deepcopy(graph_json)
    for node in compiled.get("nodes", []):
        data = node.get("data") or {}
        template = by_key.get(data.get("nodeType"))
        if template is None:
            continue
        data["nodeType"] = template.base_node_type
        data["config"] = {**(template.default_config or {}), **(data.get("config") or {})}
        node["data"] = data
    return compiled


def resolve_composite_branches(graph_json: dict[str, Any] | None) -> dict[str, Any]:
    """Compile-time 1-authored-node -> N-compiled-node expansion for the
    composable builder's "ask a question and branch on the answer" nodes
    (`whatsapp.ask_choice`, `flow.confirm` - see those modules' own
    `register_composite_branch_source` calls).

    Why this exists at all (verified against `engine/run_loop.py`): a
    `can_suspend` node's `execute()` call ends the instant it returns
    `Suspend` - resuming later calls `extract_resume_value` on that same
    node's *config*, not a second `execute()`, and then continues into
    `run.waiting_frontier` (the node's plain successors, captured *before*
    the answer was known). So a single suspending node can never itself
    branch on its own answer - the branch has to be a *separate*,
    ordinary `condition.multi_branch` node wired immediately downstream.
    Rather than making every workflow author manually wire that
    `condition.multi_branch` node themselves (with hand-typed case values
    that must exactly match whatever option ids they configured on the ask
    node - precisely the "hand-typed ids drifting out of sync" problem
    this redesign exists to eliminate), this function synthesizes it for
    them from the ask/confirm node's own declared options, at compile time.

    For each authored node whose type has a registered composite branch
    source (`engine/composite_branching.py`) that returns a non-empty
    static option list for that node's own config: adds one new
    `condition.multi_branch` node (cases = one per option, matching
    `{{<node_id>.reply.id}}` against each `option["id"]`; `default_label`
    is always "default", now optional-not-required per
    `condition_multi_branch.MultiBranchExecutor.declared_optional_output_handles`
    - the canvas never exposes a "no match" port for these auto-branch
    nodes, so nothing forces an author to wire one), retargets every one
    of the original node's own outgoing edges onto this new node (their
    `sourceHandle` is already an option id from the frontend's per-option
    handle rendering, so no relabeling is needed - only `source` changes),
    and adds one unconditional hand-off edge from the original node to its
    new branch node (no `sourceHandle` needed - see `run_loop.py`'s
    `_next_node_ids`/`_run_frontier`: only a `Branch` result's edges are
    filtered by handle; a suspending node's `remaining_frontier` and a
    plain `Success`'s frontier-advance both follow every outgoing edge
    unconditionally).

    A node whose branch source returns `None` (e.g. a `whatsapp.ask_choice`
    with a *module*-sourced `source` - the concrete option ids only exist
    at run time, so there is nothing to branch on at compile time) is left
    completely untouched: it executes as a plain single-successor
    suspending action, same as `whatsapp.ask_question` today.

    Called from `service.py` at both `publish_workflow` and
    `simulate_workflow`, immediately after `resolve_node_templates` (so
    `data.nodeType` is already each node's real, registered type by the
    time this runs) and before `WorkflowGraph.from_json`/validation - a
    synthesized `condition.multi_branch` node is validated exactly like
    any author-drawn one, no special-casing needed anywhere else.
    """
    if not graph_json:
        return dict(graph_json or {})

    pending: list[tuple[str, list[dict[str, str]]]] = []
    for node in graph_json.get("nodes") or []:
        data = node.get("data") or {}
        options_fn = get_composite_branch_source(data.get("nodeType"))
        if options_fn is None:
            continue
        try:
            options = options_fn(data.get("config") or {})
        except Exception:  # noqa: BLE001 - a malformed config is rule 1's job to report, not this pass's
            options = None
        if options:
            pending.append((node["id"], options))

    if not pending:
        return graph_json

    compiled = copy.deepcopy(graph_json)
    compiled.setdefault("nodes", [])
    compiled.setdefault("edges", [])
    existing_node_ids = {n.get("id") for n in compiled["nodes"]}
    existing_edge_ids = {e.get("id") for e in compiled["edges"]}

    for node_id, options in pending:
        branch_id = f"{node_id}__branch"
        while branch_id in existing_node_ids:
            branch_id += "_"
        existing_node_ids.add(branch_id)

        source_node = next(n for n in compiled["nodes"] if n.get("id") == node_id)
        cases = [
            {
                "label": opt["id"],
                # Plain dot-path, deliberately NOT `{{...}}`-wrapped:
                # `condition.multi_branch`'s `case.field_path` is read via
                # `engine.templating.resolve_path` directly, not the
                # `{{...}}`-aware `interpolate`/`resolve_template_value` -
                # the same "no braces" convention `EdgeFilter.field_path`
                # and `condition.field_compare` already use.
                "field_path": f"{node_id}.reply.id",
                "operator": "eq",
                "value": opt["id"],
            }
            for opt in options
        ]
        compiled["nodes"].append(
            {
                "id": branch_id,
                "type": "condition",
                "data": {
                    "nodeType": "condition.multi_branch",
                    "config": {"cases": cases, "default_label": "default"},
                },
                "position": dict(source_node.get("position") or {}),
            }
        )

        for edge in compiled["edges"]:
            if edge.get("source") == node_id:
                edge["source"] = branch_id

        link_edge_id = f"{node_id}__to_branch"
        while link_edge_id in existing_edge_ids:
            link_edge_id += "_"
        existing_edge_ids.add(link_edge_id)
        compiled["edges"].append({"id": link_edge_id, "source": node_id, "target": branch_id})

    return compiled
