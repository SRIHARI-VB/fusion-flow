"""Shared graph-fragment builders for `build_graph` functions
(`types/*.py`) - factored out after discovering the hard way (a real
end-to-end test against the live workflow-publish validator, not just
schema parsing) that this engine enforces a strict rule on any node with
declared output handles (`condition.field_compare`'s `true`/`false`):
**every required handle must be wired to EXACTLY ONE edge** - never zero,
never more than one (`workflows/validation.py::_check_invalid_branches`).
A condition can't fan its `true` handle out to several action nodes
directly, and a dangling `false` handle (nothing to do next) is a
validation error, not a no-op.

`build_keyword_condition_chain` is the one place that rule is satisfied
correctly, reused by every automation type that needs "OR over a list of
keywords, then do something on match" (both flagships built against this
task's plan need exactly this shape) so the bug this module's docstring
describes is fixed once, not once per automation type.
"""

from __future__ import annotations

from typing import Any


def build_keyword_condition_chain(
    *,
    trigger_node_id: str,
    field_path: str,
    keywords: list[str],
    operator: str,
    on_match_target_id: str,
    id_prefix: str = "match",
    start_x: float = 260,
    step_x: float = 260,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """One `condition.field_compare` node per keyword, false-chained (an OR
    over the list: keep checking the next keyword only if this one didn't
    match) - equivalent to `condition.multi_branch` with one case per
    keyword, but reusing the simpler single-comparison node type since
    every case here shares the same `field_path`/`operator`.

    Every condition's `true` handle gets its OWN single edge to
    `on_match_target_id` (never a fan-out from one handle - only one
    condition in the chain ever actually resolves `true` in a given run,
    since the run stops advancing along `false` edges the instant one
    keyword matches, so wiring every condition's `true` handle to the same
    target costs nothing at runtime and is what makes "the first keyword
    in the list matches" behave identically to "the last one matches").
    The last condition's `false` handle is wired to a generated `log.noop`
    "no match" terminal - a dangling required handle is a publish-
    validation error, not a legal "just end here".

    Returns `(nodes, edges)` ready to be concatenated onto the caller's own
    node/edge lists (which already contain `trigger_node_id` and
    `on_match_target_id`) - this function does not construct either of
    those two nodes itself.

    Empty `keywords` means "match everything" (the wizard's "All
    messages/comments" option, vs. "Specific keywords") - every calling
    automation type already validates this itself (relaxed from
    `min_length=1` to allow `[]`), so this is the one place the wildcard
    actually takes effect: no condition nodes at all, just a single direct
    edge from the trigger straight to `on_match_target_id`. This is
    correct under the same validator rule the rest of this docstring
    describes - a trigger node has no declared output handles, so an
    unconditional single edge needs no branching wiring to satisfy.
    """
    if not keywords:
        return [], [{"id": f"e-{trigger_node_id}-{on_match_target_id}", "source": trigger_node_id, "target": on_match_target_id}]

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    condition_ids: list[str] = []
    previous_node_id = trigger_node_id
    x = start_x
    for index, keyword in enumerate(keywords):
        condition_id = f"{id_prefix}-{index}"
        condition_ids.append(condition_id)
        nodes.append(
            {
                "id": condition_id,
                "type": "condition",
                "position": {"x": x, "y": 0},
                "data": {
                    "nodeType": "condition.field_compare",
                    "label": f"Matches {keyword!r}",
                    "config": {"field_path": field_path, "operator": operator, "value": keyword},
                },
            }
        )
        # The edge from the trigger (or, for index 0, nothing before it)
        # carries no handle - only branch-kind source nodes need one. Every
        # subsequent condition is reached exclusively via the previous
        # condition's `false` handle.
        edge: dict[str, Any] = {
            "id": f"e-{previous_node_id}-{condition_id}",
            "source": previous_node_id,
            "target": condition_id,
        }
        if index > 0:
            edge["sourceHandle"] = "false"
        edges.append(edge)
        previous_node_id = condition_id
        x += step_x

    for condition_id in condition_ids:
        edges.append(
            {
                "id": f"e-{condition_id}-{on_match_target_id}-true",
                "source": condition_id,
                "target": on_match_target_id,
                "sourceHandle": "true",
            }
        )

    no_match_id = f"{id_prefix}-no-match"
    nodes.append(
        {
            "id": no_match_id,
            "type": "action",
            "position": {"x": x, "y": 200},
            "data": {"nodeType": "log.noop", "label": "No Match", "config": {"message": "No keyword matched"}},
        }
    )
    edges.append(
        {
            "id": f"e-{condition_ids[-1]}-{no_match_id}",
            "source": condition_ids[-1],
            "target": no_match_id,
            "sourceHandle": "false",
        }
    )

    return nodes, edges


def build_branching_condition_chain(
    *,
    trigger_node_id: str,
    field_path: str,
    operator: str,
    cases: list[tuple[str, str]],
    id_prefix: str = "case",
    start_x: float = 260,
    step_x: float = 260,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Like `build_keyword_condition_chain`, but each case's `true` handle
    goes to ITS OWN target instead of every case converging on one shared
    target - for automation types where different matches trigger
    different actions (e.g. `instagram.referral_automation`: a different
    reply per ad/shortlink `ref` value), rather than "any of these
    keywords means the same thing".

    `cases` is `[(match_value, target_node_id), ...]`, tried in order (an
    OR-chain identical in spirit to `build_keyword_condition_chain` - only
    the first matching case in the list ever actually resolves `true` in a
    given run). Same wiring rules apply: every condition's `true` handle
    gets exactly one edge (to that case's own target), the last
    condition's `false` handle terminates in a generated `log.noop`
    ("no case matched" - see `build_keyword_condition_chain`'s docstring
    for why a dangling handle is a publish-validation error, not a legal
    no-op). Does not construct `trigger_node_id` or any of the `cases`'
    target nodes itself - same contract as `build_keyword_condition_chain`.
    """
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    condition_ids: list[str] = []
    previous_node_id = trigger_node_id
    x = start_x
    for index, (match_value, target_id) in enumerate(cases):
        condition_id = f"{id_prefix}-{index}"
        condition_ids.append(condition_id)
        nodes.append(
            {
                "id": condition_id,
                "type": "condition",
                "position": {"x": x, "y": 0},
                "data": {
                    "nodeType": "condition.field_compare",
                    "label": f"Matches {match_value!r}",
                    "config": {"field_path": field_path, "operator": operator, "value": match_value},
                },
            }
        )
        edge: dict[str, Any] = {
            "id": f"e-{previous_node_id}-{condition_id}",
            "source": previous_node_id,
            "target": condition_id,
        }
        if index > 0:
            edge["sourceHandle"] = "false"
        edges.append(edge)
        edges.append(
            {
                "id": f"e-{condition_id}-{target_id}-true",
                "source": condition_id,
                "target": target_id,
                "sourceHandle": "true",
            }
        )
        previous_node_id = condition_id
        x += step_x

    no_match_id = f"{id_prefix}-no-match"
    nodes.append(
        {
            "id": no_match_id,
            "type": "action",
            "position": {"x": x, "y": 200},
            "data": {"nodeType": "log.noop", "label": "No Match", "config": {"message": "No case matched"}},
        }
    )
    edges.append(
        {
            "id": f"e-{condition_ids[-1]}-{no_match_id}",
            "source": condition_ids[-1],
            "target": no_match_id,
            "sourceHandle": "false",
        }
    )

    return nodes, edges
