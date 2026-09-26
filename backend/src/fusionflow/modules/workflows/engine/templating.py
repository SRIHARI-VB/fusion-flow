"""Shared `{{dot.path}}` templating helpers.

Extracted for the container node types (`flow_loop.py` needs to resolve
`items_path` to an actual list, not a stringified one) rather than each
node keeping its own private copy of this logic
(`send_whatsapp_message.py`/`create_ticket.py`/`condition_field_compare.py`
each still have their own, untouched — this module doesn't retrofit them,
only new code added from this point on uses it, to avoid touching
already-tested node behavior for no functional gain).
"""

from __future__ import annotations

import re
from typing import Any

# `[\w.]+` (the original pattern) doesn't include `-`, silently failing to
# match any reference to a hyphenated node id (e.g. `{{find-customer.count}}`)
# - `\w` alone already matched every graph built with underscore-only ids,
# so this went unnoticed until a hyphenated custom node id was referenced
# through this specific module for the first time. Node ids in this
# codebase are always `[a-zA-Z0-9_-]+`, so widening to `[\w.-]+` is safe.
_TEMPLATE_RE = re.compile(r"\{\{\s*([\w.-]+)\s*\}\}")
_WHOLE_TEMPLATE_RE = re.compile(r"^\{\{\s*([\w.-]+)\s*\}\}$")


def resolve_path(data: dict[str, Any], path: str) -> Any:
    """Dot-path lookup into a nested dict, returning the raw value (may be
    a list/dict/str/int/None) - `None` if any segment is missing."""
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def interpolate(template: str, variables: dict[str, Any]) -> str:
    """Replace every `{{dot.path}}` occurrence inside `template` with its
    (stringified) resolved value, or '' if unresolved."""

    def _replace(match: "re.Match[str]") -> str:
        value = resolve_path(variables, match.group(1))
        return "" if value is None else str(value)

    return _TEMPLATE_RE.sub(_replace, template)


def resolve_template_value(template: str, variables: dict[str, Any]) -> Any:
    """If `template` is *exactly* one `{{dot.path}}` expression with
    nothing else around it, returns the raw resolved value (a list, a
    dict, a number - whatever is actually stored there), same as
    `resolve_path`. Otherwise behaves like `interpolate` and returns a
    string. This is what a config field should use when it may hold
    either a literal value or a templated reference to a non-string
    value - e.g. a Loop container's `items_path`, which must resolve to
    an actual list to iterate."""
    whole = _WHOLE_TEMPLATE_RE.match(template.strip())
    if whole is not None:
        return resolve_path(variables, whole.group(1))
    return interpolate(template, variables)


def resolve_template_value_deep(value: Any, variables: dict[str, Any]) -> Any:
    """Same as `resolve_template_value`, but recurses into dicts/lists -
    for a config field that's a nested structure with templated strings
    somewhere inside it (e.g. a button-template's `buttons: [{"title":
    ..., "payload": "{{node.field}}"}, ...]`), not a single string field.
    Only strings are ever templated; every other type (int, bool, None,
    already-resolved dict/list) passes through unchanged."""
    if isinstance(value, str):
        return resolve_template_value(value, variables)
    if isinstance(value, dict):
        return {key: resolve_template_value_deep(v, variables) for key, v in value.items()}
    if isinstance(value, list):
        return [resolve_template_value_deep(item, variables) for item in value]
    return value
