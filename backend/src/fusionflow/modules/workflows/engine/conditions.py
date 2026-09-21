"""Shared comparison-operator evaluation.

One operator set/semantics, used by `condition.field_compare`,
`condition.multi_branch`, and configurable edge filters (`engine.graph.
EdgeFilter` — see `run_loop._edge_passes_filter`) so the three places a
workflow author writes "field op value" in this engine never quietly
disagree with each other.
"""

from __future__ import annotations

import operator
from typing import Any, Callable

_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "contains": lambda haystack, needle: needle in haystack if haystack is not None else False,
    "starts_with": lambda haystack, needle: isinstance(haystack, str) and haystack.startswith(needle),
    "ends_with": lambda haystack, needle: isinstance(haystack, str) and haystack.endswith(needle),
}


def evaluate_condition(op: str, actual: Any, expected: Any) -> bool:
    """`True`/`False` for `actual <op> expected`. An unknown `op` falls
    back to `eq` (defensive — callers with a Pydantic `Literal[...]`-typed
    operator field can never actually hit this, but a plain `str`-typed
    one, like `condition.multi_branch`'s per-case operator or an edge
    filter's, could). A `TypeError` from comparing mismatched types (e.g.
    `None > 5`) is treated as "did not match" rather than raised."""
    compare = _OPERATORS.get(op, operator.eq)
    try:
        return bool(compare(actual, expected))
    except TypeError:
        return False
