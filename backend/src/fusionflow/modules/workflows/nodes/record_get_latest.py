"""`records.get_latest` — "the newest record matching these filters, if
any", for any fixed module or tenant-defined custom object type, flattened
to one object.

`records.query` (operation="list") already returns the newest-first page
via each adapter's own ordering, but as `{"items": [...], "count": N}` -
a *list*. The templating engine's `resolve_path` only ever traverses
dicts (`isinstance(current, dict)`), so `{{some-query-node.items.0.foo}}`
can never resolve - there is no "list, then take the first element"
available to a workflow author anywhere in this engine. This node is
`records.query` plus that one missing step: force `limit=1` and unwrap
the single-element list (or lack of one) into `{"found": bool, "item":
dict | None}`, the same flattening shape `find_or_create_customer`/
`tickets.get_latest_for_customer` already establish for "zero-or-one
result" lookups - generalized here to any module instead of one
hardcoded ticket lookup, so a workflow author never has to reach for a
bespoke node just to ask "what's the newest X for this filter" again.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.module_registry import interpolate_dict_values, resolve_adapter
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "found": {"type": "boolean"},
        "item": {"type": ["object", "null"]},
    },
}


class GetLatestRecordConfig(BaseModel):
    module: str = Field(min_length=1, description="Which kind of record - a fixed module or one of your own.")
    filters: dict[str, Any] = Field(default_factory=dict, description="e.g. {'customer_id': '{{...}}', 'status': 'requested'}.")


class GetLatestRecordExecutor(NodeExecutor):
    node_type = "records.get_latest"
    kind = "action"
    category = "Records"
    palette_group = "Records"
    icon = "database"
    label = "Get Latest Record"
    description = "The newest record matching these filters, if any (Products, Orders, or one you created yourself) - flattened to one object, not a list."
    config_model = GetLatestRecordConfig
    applicable_purposes = ["automation", "broadcast"]
    output_schema = _OUTPUT_SCHEMA

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = GetLatestRecordConfig.model_validate(context.config)
        adapter = await resolve_adapter(context.session, tenant_id=context.tenant_id, module_key=config.module)
        if adapter is None:
            return Failure(f"unknown module {config.module!r}")

        filters = interpolate_dict_values(config.filters, context.variables)
        try:
            items = await adapter.list(context.session, tenant_id=context.tenant_id, filters=filters, limit=1)
        except (ValueError, LookupError) as exc:
            return Failure(str(exc))

        if not items:
            return Success(output={"found": False, "item": None})
        return Success(output={"found": True, "item": items[0]})


node_executor_registry.register(GetLatestRecordExecutor())
