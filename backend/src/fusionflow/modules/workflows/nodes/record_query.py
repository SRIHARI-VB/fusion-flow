"""`records.query` — the composable-builder redesign's friendly front door
onto `module.list`/`module.get`: one node, a `module` picker (see
`GET /workflows/modules`/`module_catalog.py` — fixed modules and a tenant's
own custom object types side by side) and an `operation` choice, instead of
two separate generic node types an author has to already know exist.
Delegates to the exact same `resolve_adapter` lookup `module.list`/
`module.get` use, so this is purely a friendlier config surface over
identical dispatch — no new business logic.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

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
from fusionflow.modules.workflows.engine.templating import resolve_template_value

_OUTPUT_SCHEMA = {"type": "object"}


class RecordQueryConfig(BaseModel):
    module: str = Field(min_length=1, description="Which kind of record - a fixed module or one of your own.")
    operation: Literal["list", "get"] = "list"
    filters: dict[str, Any] = Field(default_factory=dict, description="Only used when operation='list'.")
    limit: int = Field(default=DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT, description="Only used when operation='list'.")
    item_id: str | None = Field(default=None, description="Record id. Required when operation='get'.")


class RecordQueryExecutor(NodeExecutor):
    node_type = "records.query"
    kind = "action"
    category = "Records"
    palette_group = "Records"
    icon = "database"
    label = "Find or Get a Record"
    description = "Looks up records (a list, or one by id) from any of your modules - Products, Orders, or one you created yourself."
    config_model = RecordQueryConfig
    output_schema = _OUTPUT_SCHEMA

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = RecordQueryConfig.model_validate(context.config)
        adapter = await resolve_adapter(context.session, tenant_id=context.tenant_id, module_key=config.module)
        if adapter is None:
            return Failure(f"unknown module {config.module!r}")

        if config.operation == "list":
            limit = min(config.limit, MAX_LIST_LIMIT)
            filters = interpolate_dict_values(config.filters, context.variables)
            try:
                items = await adapter.list(context.session, tenant_id=context.tenant_id, filters=filters, limit=limit)
            except (ValueError, LookupError) as exc:
                return Failure(str(exc))
            return Success(output={"items": items, "count": len(items)})

        if not config.item_id:
            return Failure("item_id is required when operation='get'")
        resolved_id = resolve_template_value(config.item_id, context.variables)
        try:
            item_id = uuid.UUID(str(resolved_id))
        except ValueError:
            return Failure(f"item_id {resolved_id!r} is not a valid UUID")

        item = await adapter.get(context.session, tenant_id=context.tenant_id, item_id=item_id)
        if item is None:
            return Failure(f"{config.module} record {item_id} not found")
        return Success(output={"item": item})


node_executor_registry.register(RecordQueryExecutor())
