"""Unit tests for `engine.template_resolution.resolve_composite_branches`
(composable-builder redesign, Phase 4) - the compile-time 1-authored-node
-> N-compiled-node expansion for `whatsapp.ask_choice`/`flow.confirm`.
Operates on raw graph JSON dicts directly (same convention as
`resolve_node_templates`), so these tests build that shape by hand rather
than going through `WorkflowGraph.from_json`.
"""

from __future__ import annotations

import uuid

import pytest

from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.template_resolution import resolve_composite_branches
from fusionflow.modules.workflows import validation

# Importing these registers their composite branch sources as a side
# effect (module import time), exactly like importing `nodes/__init__.py`
# does for real execution - needed here since these tests exercise the
# registry-driven expansion, not a specific executor's `execute()`.
from fusionflow.modules.workflows.nodes import flow_confirm, whatsapp_ask_choice  # noqa: F401

# No module-level `pytestmark` - this file mixes sync `resolve_composite_
# branches` tests with one async validation test, and `asyncio_mode =
# "auto"` (pyproject.toml) already auto-detects the coroutine one.


class _FakeSession:
    async def get(self, model, ident):
        return None


def _node(node_id: str, node_type: str, config: dict | None = None) -> dict:
    return {"id": node_id, "type": node_type, "data": {"nodeType": node_type, "config": config or {}}}


def _edge(edge_id: str, source: str, target: str, source_handle: str | None = None) -> dict:
    edge = {"id": edge_id, "source": source, "target": target}
    if source_handle is not None:
        edge["sourceHandle"] = source_handle
    return edge


def test_static_ask_choice_gets_a_synthesized_multi_branch_node() -> None:
    graph = {
        "nodes": [
            _node("trigger", "manual.test_trigger"),
            _node(
                "ask",
                "whatsapp.ask_choice",
                {
                    "connector_instance_id": "x",
                    "to": "y",
                    "question": "Size?",
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

    compiled = resolve_composite_branches(graph)

    node_ids = {n["id"] for n in compiled["nodes"]}
    assert "ask__branch" in node_ids
    branch_node = next(n for n in compiled["nodes"] if n["id"] == "ask__branch")
    assert branch_node["data"]["nodeType"] == "condition.multi_branch"
    cases = branch_node["data"]["config"]["cases"]
    assert cases == [
        {"label": "small", "field_path": "ask.reply.id", "operator": "eq", "value": "small"},
        {"label": "large", "field_path": "ask.reply.id", "operator": "eq", "value": "large"},
    ]
    assert branch_node["data"]["config"]["default_label"] == "default"

    # The two original branch edges now originate from the synthesized
    # node, sourceHandle unchanged; a new unconditional hand-off edge links
    # "ask" -> "ask__branch".
    edges_by_id = {e["id"]: e for e in compiled["edges"]}
    assert edges_by_id["e2"]["source"] == "ask__branch"
    assert edges_by_id["e2"]["sourceHandle"] == "small"
    assert edges_by_id["e3"]["source"] == "ask__branch"
    assert edges_by_id["e3"]["sourceHandle"] == "large"
    handoff_edges = [e for e in compiled["edges"] if e["source"] == "ask" and e["target"] == "ask__branch"]
    assert len(handoff_edges) == 1
    assert "sourceHandle" not in handoff_edges[0]

    # Original graph must be left untouched (never mutated in place).
    assert compiled is not graph
    assert len(graph["nodes"]) == 4
    assert len(graph["edges"]) == 3
    assert graph["edges"][1]["source"] == "ask"


def test_module_sourced_ask_choice_is_left_untouched() -> None:
    graph = {
        "nodes": [
            _node("trigger", "manual.test_trigger"),
            _node(
                "ask",
                "whatsapp.ask_choice",
                {
                    "connector_instance_id": "x",
                    "to": "y",
                    "question": "Which product?",
                    "source": {"kind": "module", "module": "products"},
                },
            ),
            _node("after", "log.noop"),
        ],
        "edges": [_edge("e1", "trigger", "ask"), _edge("e2", "ask", "after")],
    }

    compiled = resolve_composite_branches(graph)

    # No expansion happened at all - the exact same object comes back.
    assert compiled is graph
    assert len(compiled["nodes"]) == 3
    assert not any(n["id"].endswith("__branch") for n in compiled["nodes"])


def test_flow_confirm_always_gets_the_fixed_yes_no_cases() -> None:
    graph = {
        "nodes": [
            _node("trigger", "manual.test_trigger"),
            _node("confirm", "flow.confirm", {"connector_instance_id": "x", "to": "y", "question": "Proceed?"}),
            _node("yes_path", "log.noop"),
            _node("no_path", "log.noop"),
        ],
        "edges": [
            _edge("e1", "trigger", "confirm"),
            _edge("e2", "confirm", "yes_path", source_handle="yes"),
            _edge("e3", "confirm", "no_path", source_handle="no"),
        ],
    }

    compiled = resolve_composite_branches(graph)

    branch_node = next(n for n in compiled["nodes"] if n["id"] == "confirm__branch")
    cases = branch_node["data"]["config"]["cases"]
    assert cases == [
        {"label": "yes", "field_path": "confirm.reply.id", "operator": "eq", "value": "yes"},
        {"label": "no", "field_path": "confirm.reply.id", "operator": "eq", "value": "no"},
    ]


def test_synthesized_branch_id_avoids_collision_with_an_existing_node_id() -> None:
    graph = {
        "nodes": [
            _node("trigger", "manual.test_trigger"),
            _node("ask", "flow.confirm", {"connector_instance_id": "x", "to": "y", "question": "Proceed?"}),
            # Deliberately collides with the default synthesized id.
            _node("ask__branch", "log.noop"),
        ],
        "edges": [_edge("e1", "trigger", "ask"), _edge("e2", "ask", "ask__branch")],
    }

    compiled = resolve_composite_branches(graph)

    branch_nodes = [n for n in compiled["nodes"] if n["data"]["nodeType"] == "condition.multi_branch"]
    assert len(branch_nodes) == 1
    assert branch_nodes[0]["id"] != "ask__branch"


def test_graph_with_no_composite_nodes_is_returned_unchanged() -> None:
    graph = {
        "nodes": [_node("trigger", "manual.test_trigger"), _node("noop", "log.noop")],
        "edges": [_edge("e1", "trigger", "noop")],
    }
    assert resolve_composite_branches(graph) is graph


async def test_compiled_graph_with_default_unwired_passes_publish_validation() -> None:
    """Part A's `declared_optional_output_handles` relaxation is what makes
    this possible: the canvas never exposes a "no match" port for an
    auto-branch composite node, so an author has no way to wire the
    synthesized `condition.multi_branch`'s `default` handle even if they
    wanted to - it must not be a required, exactly-once-wired handle."""
    authored = {
        "nodes": [
            _node("trigger", "manual.test_trigger"),
            _node(
                "confirm",
                "flow.confirm",
                {"connector_instance_id": str(uuid.uuid4()), "to": "{{trigger.from}}", "question": "Proceed?"},
            ),
            _node("yes_path", "log.noop"),
            _node("no_path", "log.noop"),
        ],
        "edges": [
            _edge("e1", "trigger", "confirm"),
            _edge("e2", "confirm", "yes_path", source_handle="yes"),
            _edge("e3", "confirm", "no_path", source_handle="no"),
            # Deliberately no edge wired to the synthesized "default" handle.
        ],
    }

    compiled_graph = WorkflowGraph.from_json(resolve_composite_branches(authored))
    result = await validation.validate_for_publish(_FakeSession(), tenant_id=uuid.uuid4(), graph=compiled_graph)

    # Scoped to rule 4 only - a random connector_instance_id predictably
    # fails rule 2 (disconnected_connector_reference) against a session
    # with no real connector rows, which is irrelevant to what this test
    # is proving (see test file convention: other rule-4 tests in
    # `test_workflows_engine.py` assert on `i.rule == "invalid_branches"`
    # specifically, not on overall `has_errors`, for the same reason).
    assert not any(i.rule == "invalid_branches" for i in result.issues)
