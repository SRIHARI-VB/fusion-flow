"""`ModuleQueryAdapter` ABC + `ModuleQueryRegistry` — the module-CRUD analogue
of `modules/connectors/base.py`'s `ConnectorAdapter`/`ConnectorRegistry`.

Phase 6's architecture decision (see the plan doc): 9 fixed modules x up to
4 operations is ~30 structurally-identical operations varying only by
target module and fields - exactly the case for a small number of generic
`NodeExecutor`s (`module.list`/`module.get`/`module.create`/`module.update`,
see `modules/workflows/nodes/module_*.py`) dispatching through a per-module
adapter registry, rather than ~30 bespoke node types.

Each adapter is a thin wrapper around that module's own `service.py`
functions - it owns no state and does no I/O itself. `create`/`update`
default to raising `NotImplementedError`, exactly mirroring
`ConnectorAdapter.perform_action`'s "not every provider supports every
action" shape - here, "not every module supports every CRUD verb"
(Payments: list/get only; Orders: list/get/update(status-only), no create -
see this phase's plan for why).
"""

from __future__ import annotations

import abc
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.workflows.engine.templating import resolve_template_value


class ModuleQueryAdapter(abc.ABC):
    """One implementation per fixed module. See module docstring."""

    #: Matches the `connector_types.key` catalog row (category=FEATURE)
    #: this adapter serves, e.g. "products", "customers".
    module_key: str

    @abc.abstractmethod
    async def list(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        """Return JSON-serializable dicts (already-serialized via the
        module's own `*Out` schema), newest first, capped at `limit`."""

    @abc.abstractmethod
    async def get(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Return a single JSON-serializable dict, or None if not found."""

    async def create(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError(f"module {self.module_key!r} does not support create")

    async def update(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        raise NotImplementedError(f"module {self.module_key!r} does not support update")


class ModuleQueryRegistry:
    """Module-level `module_key -> ModuleQueryAdapter` map, mirroring
    `ConnectorRegistry`'s `register`/`get`/`get_or_none` exactly."""

    def __init__(self) -> None:
        self._adapters: dict[str, ModuleQueryAdapter] = {}

    def register(self, adapter: ModuleQueryAdapter) -> None:
        self._adapters[adapter.module_key] = adapter

    def get(self, module_key: str) -> ModuleQueryAdapter:
        try:
            return self._adapters[module_key]
        except KeyError as exc:
            raise LookupError(f"no module query adapter registered for module_key={module_key!r}") from exc

    def get_or_none(self, module_key: str) -> ModuleQueryAdapter | None:
        return self._adapters.get(module_key)

    def registered_keys(self) -> list[str]:
        return list(self._adapters.keys())


#: Process-wide singleton. Adapters are stateless (each call carries its own
#: session/tenant_id), matching `connectors.base.registry`'s rationale.
registry = ModuleQueryRegistry()


async def resolve_adapter(
    session: AsyncSession | None, *, tenant_id: uuid.UUID, module_key: str
) -> ModuleQueryAdapter | None:
    """Shared `module.*`/`records.*` node lookup: try the global, fixed-module
    registry first; if that misses, fall back to a tenant-defined custom
    object type (`business_objects.workflow_adapter.resolve`) - a per-request
    lookup, not a registry entry, because that registry is a process-wide
    singleton and a tenant's object-type key must never leak across tenants
    (see `business_objects/workflow_adapter.py`'s module docstring for the
    full reasoning). `session=None` is only ever a sessionless unit test
    exercising the "truly unknown module" path with no database - real
    execution always has a session.

    Was previously duplicated inline, one copy each, in `module_list.py`/
    `module_get.py`/`module_create.py`/`module_update.py`; extracted here so
    `records.query`/`records.upsert` (and any future generic module node)
    share one lookup instead of a fourth/fifth copy. Import of
    `business_objects.workflow_adapter` is deliberately local to this
    function, not top-level - that module imports `ModuleQueryAdapter` from
    *this* one, so a top-level import here would be a circular import.
    """
    adapter = registry.get_or_none(module_key)
    if adapter is not None or session is None:
        return adapter

    from fusionflow.modules.business_objects import workflow_adapter as business_objects_workflow_adapter

    return await business_objects_workflow_adapter.resolve(session, tenant_id=tenant_id, key=module_key)

#: The hard, server-enforced pagination ceiling for `module.list`, regardless
#: of what a node's own `config.limit` requests - confirmed user decision
#: (Phase 6 plan): "fixed hard cap, configurable up to a ceiling."
MAX_LIST_LIMIT = 100
DEFAULT_LIST_LIMIT = 20


def interpolate_dict_values(values: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    """Resolve `{{dot.path}}` templating in each string value of a
    `filters`/`fields` dict (non-string values pass through unchanged) -
    shared by `module.list`/`module.create`/`module.update` so a workflow
    can chain a prior step's output into a filter/field value (e.g. filter
    orders by `{{find_customer.customer.id}}`). Mirrors
    `connector_action.py`'s own private `_interpolate_params` helper."""
    return {
        key: resolve_template_value(value, variables) if isinstance(value, str) else value
        for key, value in values.items()
    }
