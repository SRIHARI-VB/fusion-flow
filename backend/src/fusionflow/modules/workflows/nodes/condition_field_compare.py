"""`condition.field_compare` — compares a field in the running variable
context against a configured value and branches to a `true`/`false`
output handle. Self-contained: works against whatever is already in the
run's variable context (trigger payload + prior node outputs), no external
dependency."""

from __future__ import annotations

import operator
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.registry import (
    Branch,
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    node_executor_registry,
)

_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "contains": lambda haystack, needle: needle in haystack if haystack is not None else False,
}


class FieldCompareConfig(BaseModel):
    field_path: str = Field(
        min_length=1,
        description=(
            "Dot-separated path into the run's variable context, e.g. "
            "'trigger.message.text' or '<node_id>.output_field'."
        ),
    )
    operator: Literal["eq", "neq", "gt", "gte", "lt", "lte", "contains"] = "eq"
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
        compare = _OPERATORS[config.operator]
        try:
            matched = bool(compare(actual, config.value))
        except TypeError:
            # Mismatched types (e.g. comparing None with `gt`) - treat as
            # "did not match" rather than crashing the node.
            matched = False
        handle = "true" if matched else "false"
        return Branch(
            selected_edge_handles=[handle],
            output={"field_path": config.field_path, "actual": actual, "matched": matched},
        )


node_executor_registry.register(FieldCompareExecutor())
