"""Shared comparison-operator evaluation.

One operator set/semantics, used by `condition.field_compare`,
`condition.multi_branch`, and configurable edge filters (`engine.graph.
EdgeFilter` — see `run_loop._edge_passes_filter`) so the three places a
workflow author writes "field op value" in this engine never quietly
disagree with each other.
"""

from __future__ import annotations

import operator
import re
from typing import Any, Callable

_OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "eq": operator.eq,
    "neq": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "contains": lambda haystack, needle: needle in haystack if haystack is not None else False,
    # Case-insensitive sibling of "contains", added because the
    # case-sensitive check above was silently failing to match customer
    # replies typed in natural capitalization (e.g. "Thanks!"/"OK"/"COST")
    # against lowercase-configured keyword gates. Purely additive - other
    # tenants' workflows may already depend on "contains" staying
    # case-sensitive, so that entry is left untouched. `str(...)` on both
    # sides before `.casefold()` so a non-string haystack/needle (e.g. an
    # int actual value) degrades to a normal substring check instead of
    # raising, same None-safety shape as "contains" itself.
    "icontains": (
        lambda haystack, needle: str(needle).casefold() in str(haystack).casefold() if haystack is not None else False
    ),
    "starts_with": lambda haystack, needle: isinstance(haystack, str) and haystack.startswith(needle),
    "ends_with": lambda haystack, needle: isinstance(haystack, str) and haystack.endswith(needle),
    # Word-boundary sibling of "icontains" - added because a short, common
    # keyword (e.g. "hi", "hey") matched via plain substring search false-
    # positives on any longer word that happens to contain those letters in
    # sequence ("this", "which", "shirt", "they" all contain "hi"/"hey"),
    # misclassifying an unrelated message as a greeting before it ever
    # reaches the real intent keywords. `\b` in Python's `re` is Unicode-
    # aware by default, so this still only anchors on non-word-character
    # boundaries (whitespace/punctuation/string edges) exactly like a
    # human would read "is this word standalone". A non-string haystack
    # degrades to `False` (nothing to search), matching "icontains"'s
    # None-safety shape.
    "icontains_word": (
        lambda haystack, needle: bool(re.search(rf"\b{re.escape(str(needle))}\b", str(haystack), re.IGNORECASE))
        if haystack is not None
        else False
    ),
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
