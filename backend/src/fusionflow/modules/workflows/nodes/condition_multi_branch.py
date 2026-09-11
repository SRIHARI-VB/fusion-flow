"""`condition.multi_branch` — generalizes `condition.field_compare` from a
fixed true/false to N config-declared cases, each with its own field/
operator/value and its own output handle. A workflow author adds a new
branch by editing this node's config (adding a case) instead of adding a
new node type or touching engine code — the condition-branching half of
Part D's "catalog/config, not code" extensibility answer.

The first node type in this codebase whose output handles are genuinely
config-dependent — see `declared_output_handles` below and
`registry.NodeExecutor.declared_output_handles`'s docstring for how
validation.py's rule 4 stays correct for both the static and dynamic
cases through one shared code path.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.conditions import evaluate_condition
from fusionflow.modules.workflows.engine.registry import (
    Branch,
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import resolve_path

_OUTPUT_SCHEMA = {"type": "object", "properties": {"matched_case": {"type": "string"}}}


class MultiBranchCase(BaseModel):
    label: str = Field(
        min_length=1, description="Also the output handle id - must be unique among this node's cases."
    )
    field_path: str = Field(min_length=1)
    operator: str = "eq"
    value: Any = None


class MultiBranchConfig(BaseModel):
    cases: list[MultiBranchCase] = Field(min_length=1)
    default_label: str = Field(default="default", description="Handle used when no case matches.")


class MultiBranchExecutor(NodeExecutor):
    node_type = "condition.multi_branch"
    kind = "condition"
    category = "Conditions"
    label = "Multi-Branch Condition"
    description = (
        "Branches to the first matching case (in declared order), or the default handle if none "
        "match. Add or remove cases in this node's config instead of adding new condition nodes."
    )
    config_model = MultiBranchConfig
    output_schema = _OUTPUT_SCHEMA

    def declared_output_handles(self, config: dict[str, Any]) -> list[str] | None:
        try:
            parsed = MultiBranchConfig.model_validate(config)
        except Exception:
            # Malformed config is already reported by rule 1
            # (missing_required_fields) - returning None here just avoids
            # this rule piling on a second, less useful error about it.
            return None
        return [case.label for case in parsed.cases]

    def declared_optional_output_handles(self, config: dict[str, Any]) -> list[str] | None:
        """The "no case matched" handle is wireable but not required — an
        author may legitimately want "just stop" as the no-match outcome
        instead of routing it anywhere (see `NodeExecutor.
        declared_optional_output_handles`'s docstring). Also what lets a
        compile-time-synthesized multi_branch node (see
        `engine/composite_branching.py`, whose cases come from a
        `whatsapp.ask_choice`/`flow.confirm` node's own options — a set
        the canvas never exposes a "no match" port for) still pass
        publish validation without the author ever wiring `default`."""
        try:
            parsed = MultiBranchConfig.model_validate(config)
        except Exception:
            return None
        return [parsed.default_label]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = MultiBranchConfig.model_validate(context.config)
        for case in config.cases:
            actual = resolve_path(context.variables, case.field_path)
            matched = evaluate_condition(case.operator, actual, case.value)
            if matched:
                return Branch(
                    selected_edge_handles=[case.label], output={"matched_case": case.label, "actual": actual}
                )
        return Branch(selected_edge_handles=[config.default_label], output={"matched_case": None})


node_executor_registry.register(MultiBranchExecutor())
