"""`records.upsert` — the composable-builder redesign's friendly front door
onto `module.create`/`module.update`: one node, a `module` picker (see
`GET /workflows/modules`/`module_catalog.py`) and an `operation` choice,
instead of two separate generic node types. Reuses `module_create.py`'s own
`_COUNT_FNS` resource-limit map rather than a second copy - same plan/limit
enforcement, one source of truth.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.workflows.engine.module_registry import interpolate_dict_values, resolve_adapter
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import resolve_template_value
from fusionflow.modules.workflows.nodes.module_create import _COUNT_FNS

_OUTPUT_SCHEMA = {"type": "object", "properties": {"item": {"type": "object"}}}


class RecordUpsertConfig(BaseModel):
    module: str = Field(min_length=1, description="Which kind of record - a fixed module or one of your own.")
    operation: Literal["create", "update"] = "create"
    item_id: str | None = Field(default=None, description="Record id. Required when operation='update'.")
    fields: dict[str, Any] = Field(default_factory=dict)


class RecordUpsertExecutor(NodeExecutor):
    node_type = "records.upsert"
    kind = "action"
    category = "Records"
    palette_group = "Records"
    icon = "file-plus"
    label = "Create or Update a Record"
    description = "Creates a new record, or updates an existing one, in any of your modules - Orders, Customers, or one you created yourself."
    config_model = RecordUpsertConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = RecordUpsertConfig.model_validate(context.config)
        adapter = await resolve_adapter(context.session, tenant_id=context.tenant_id, module_key=config.module)
        if adapter is None:
            return Failure(f"unknown module {config.module!r}")

        fields = interpolate_dict_values(config.fields, context.variables)

        if config.operation == "create":
            count_fn = _COUNT_FNS.get(config.module)
            if count_fn is not None:
                limit = await admin_service.get_resource_limit(
                    context.session, tenant_id=context.tenant_id, resource_key=config.module
                )
                if limit is not None:
                    current = await count_fn(context.session, context.tenant_id)
                    if current >= limit:
                        return Failure(f"tenant has reached its plan's limit of {limit} for {config.module!r}")
            try:
                item = await adapter.create(context.session, tenant_id=context.tenant_id, fields=fields)
            except NotImplementedError as exc:
                return Failure(str(exc))
            except (ValueError, ValidationError) as exc:
                return Failure(str(exc))
            return Success(output={"item": item})

        if not config.item_id:
            return Failure("item_id is required when operation='update'")
        resolved_id = resolve_template_value(config.item_id, context.variables)
        try:
            item_id = uuid.UUID(str(resolved_id))
        except ValueError:
            return Failure(f"item_id {resolved_id!r} is not a valid UUID")

        try:
            item = await adapter.update(context.session, tenant_id=context.tenant_id, item_id=item_id, fields=fields)
        except NotImplementedError as exc:
            return Failure(str(exc))
        except (ValueError, ValidationError) as exc:
            return Failure(str(exc))

        if item is None:
            return Failure(f"{config.module} record {item_id} not found")
        return Success(output={"item": item})


node_executor_registry.register(RecordUpsertExecutor())
