"""`condition.field_compare` — compares a field in the running variable
context against a configured value and branches to a `true`/`false`
output handle. Self-contained: works against whatever is already in the
run's variable context (trigger payload + prior node outputs), no external
dependency."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.conditions import evaluate_condition
from fusionflow.modules.workflows.engine.registry import (
    Branch,
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    node_executor_registry,
)


#: Shared with `condition.multi_branch`'s `MultiBranchCase.operator` -
#: every operator a condition node in this codebase can compare with, kept
#: in exactly one place so the two node types can never drift apart.
ComparisonOperator = Literal[
    "eq", "neq", "gt", "gte", "lt", "lte", "contains", "icontains", "icontains_word", "starts_with", "ends_with"
]


class FieldCompareConfig(BaseModel):
    field_path: str = Field(
        min_length=1,
        description=(
            "The value to check - usually the trigger's data or the result of an earlier "
            "step, e.g. 'Ask a Question -> reply'."
        ),
    )
    operator: ComparisonOperator = "eq"
    value: Any = None


def _resolve_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


class FieldCompareExecutor(NodeExecutor):
    node_type = "condition.field_compare"
    kind = "condition"
    category = "Conditions"
    label = "Compare Field"
    description = "Compares a field in the running context against a configured value and branches true/false."
    config_model = FieldCompareConfig
    output_handles = ["true", "false"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = FieldCompareConfig.model_validate(context.config)
        actual = _resolve_path(context.variables, config.field_path)
        matched = evaluate_condition(config.operator, actual, config.value)
        handle = "true" if matched else "false"
        return Branch(
            selected_edge_handles=[handle],
            output={"field_path": config.field_path, "actual": actual, "matched": matched},
        )


node_executor_registry.register(FieldCompareExecutor())
