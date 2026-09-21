"""`PredefinedAutomationType` + `PredefinedAutomationRegistry`.

One entry per guided automation type (e.g. `instagram.comment_automation`),
registered by whichever module defines it - see
`instagram_comment_automation.py` for the first one. Mirrors
`connectors.base.ConnectorRegistry` deliberately: a "registry of pluggable
things, each contributing a build function" is already this codebase's
established shape for exactly this kind of extensibility (see also the
node-executor registry in `workflows/engine/registry.py`).

`build_graph` is the entire "wizard config -> workflow graph" contract:
given the wizard's `config` dict, return a `{"nodes": [...], "edges":
[...]}` structure using already-registered node types (trigger + condition
+ `connector.action`, typically) - the exact same shape a hand-drawn canvas
graph produces, just assembled in code instead of dragged. Adding a new
automation type is one more registration here, never a change to the
workflow engine.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class PredefinedAutomationType:
    automation_type: str
    #: Which connector this type applies to - `service.py` rejects a
    #: create/update whose connector instance's type doesn't match.
    connector_type_key: str
    label: str
    description: str
    #: `(config, connector_instance_id) -> {"nodes": [...], "edges": [...]}`
    #: - see module docstring. `connector_instance_id` is passed
    #: separately rather than folded into `config` since it already lives
    #: on `PredefinedAutomation.connector_instance_id` (a real column, not
    #: part of the wizard's own re-editable answers) - every `connector.
    #: action` node the builder emits needs it in its own config.
    build_graph: Callable[[dict[str, Any], uuid.UUID], dict[str, Any]]


class PredefinedAutomationRegistry:
    def __init__(self) -> None:
        self._types: dict[str, PredefinedAutomationType] = {}

    def register(self, spec: PredefinedAutomationType) -> None:
        self._types[spec.automation_type] = spec

    def get(self, automation_type: str) -> PredefinedAutomationType:
        try:
            return self._types[automation_type]
        except KeyError as exc:
            raise LookupError(f"no predefined automation type registered for {automation_type!r}") from exc

    def get_or_none(self, automation_type: str) -> PredefinedAutomationType | None:
        return self._types.get(automation_type)

    def for_connector_type(self, connector_type_key: str) -> list[PredefinedAutomationType]:
        return [t for t in self._types.values() if t.connector_type_key == connector_type_key]

    def all_types(self) -> list[PredefinedAutomationType]:
        return list(self._types.values())


#: Process-wide singleton - safe: every entry is a pure function reference,
#: mirroring `connectors.base.registry`'s identical "stateless, one per
#: process" rationale.
registry = PredefinedAutomationRegistry()
