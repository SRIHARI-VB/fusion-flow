"""`module.list` — generic node type: list rows from any fixed module
(products/services/coupons/offers/customers/orders/payments/tickets/kb)
through its registered `ModuleQueryAdapter` (see
`modules/workflows/engine/module_registry.py`).

`limit` is always server-clamped to `MAX_LIST_LIMIT` regardless of what the
node's config requests - confirmed user decision (Phase 6 plan): every
module's list function otherwise returns an unbounded result set, which
would be a real production hazard pulled into a run's variable context.

`filters` is a raw JSON object in this v1 (mirrors `connector.action`'s
`params` dict tradeoff - see that node's docstring) - each adapter
interprets whichever keys it recognizes and ignores the rest.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.module_registry import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    interpolate_dict_values,
    resolve_adapter,
)
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.nodes import _module_adapters  # noqa: F401 - side-effect import


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array"}, "count": {"type": "integer"}},
}


class ModuleListConfig(BaseModel):
    module: str = Field(min_length=1, description="Catalog module key, e.g. 'products', 'customers'.")
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT)


class ModuleListExecutor(NodeExecutor):
    node_type = "module.list"
    kind = "action"
    category = "Data"
    label = "List Module Records"
    description = "Lists rows from a fixed module (Products, Customers, Orders, ...), filtered and capped."
    config_model = ModuleListConfig
    output_schema = _OUTPUT_SCHEMA

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ModuleListConfig.model_validate(context.config)
        adapter = await resolve_adapter(context.session, tenant_id=context.tenant_id, module_key=config.module)
        if adapter is None:
            return Failure(f"unknown module {config.module!r}")

        limit = min(config.limit, MAX_LIST_LIMIT)
        filters = interpolate_dict_values(config.filters, context.variables)
        try:
            items = await adapter.list(
                context.session, tenant_id=context.tenant_id, filters=filters, limit=limit
            )
        except (ValueError, LookupError) as exc:
            return Failure(str(exc))

        return Success(output={"items": items, "count": len(items)})


node_executor_registry.register(ModuleListExecutor())
