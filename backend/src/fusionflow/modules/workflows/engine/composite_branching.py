"""`node_type -> "static branch options" function` registry — the plugin
surface `engine/template_resolution.py::resolve_composite_branches` reads
to decide which authored nodes get compile-time-expanded into themselves
plus a synthesized `condition.multi_branch` node (see that function's
docstring for the full picture).

Mirrors `NodeExecutorRegistry`/`ModuleQueryRegistry`'s "small
process-wide singleton, populated by import-for-side-effect" pattern
already used twice in this codebase — a composite node module (e.g.
`nodes/whatsapp_ask_choice.py`, `nodes/flow_confirm.py`) calls
`register_composite_branch_source(...)` at import time, the same way it
calls `node_executor_registry.register(...)`.

Kept as its own tiny module (not folded into `template_resolution.py`
itself) so that file stays focused on orchestration/compilation, not
registration bookkeeping.
"""

from __future__ import annotations

from typing import Any, Callable

#: `(node_config) -> [{"id": ..., "label": ...}, ...]` for a STATIC,
#: known-at-publish-time option set, or `None` if this node instance's
#: options aren't statically knowable (e.g. a `whatsapp.ask_choice` node
#: whose `source.kind == "module"` - the concrete rows only exist at run
#: time, so there is nothing to branch on at compile time; the node then
#: just executes as a plain single-successor suspending action - no
#: expansion, no error). Must never raise - malformed config is reported
#: separately by publish-time validation's own rules, not here.
CompositeBranchOptionsFn = Callable[[dict[str, Any]], "list[dict[str, str]] | None"]

_registry: dict[str, CompositeBranchOptionsFn] = {}


def register_composite_branch_source(node_type: str, fn: CompositeBranchOptionsFn) -> None:
    _registry[node_type] = fn


def get_composite_branch_source(node_type: str) -> CompositeBranchOptionsFn | None:
    return _registry.get(node_type)
