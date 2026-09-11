"""`module.update` — generic node type: partially update a row in any fixed
module that supports it through its registered `ModuleQueryAdapter`.

Orders' adapter rejects any field other than `status` (see
`orders/workflow_adapter.py`) - surfaced here as a clean `Failure` via the
adapter raising `ValueError`, not a workflow-engine-level special case.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field, ValidationError

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
from fusionflow.modules.workflows.nodes import _module_adapters  # noqa: F401 - side-effect import


_OUTPUT_SCHEMA = {"type": "object", "properties": {"item": {"type": "object"}}}


class ModuleUpdateConfig(BaseModel):
    module: str = Field(min_length=1, description="Catalog module key, e.g. 'products', 'orders'.")
    item_id: str = Field(min_length=1, description="Row id. May use '{{dot.path}}' templating.")
    fields: dict[str, Any] = Field(default_factory=dict)


class ModuleUpdateExecutor(NodeExecutor):
    node_type = "module.update"
    kind = "action"
    category = "Data"
    label = "Update Module Record"
    description = "Partially updates a row in a fixed module (Orders is restricted to status only)."
    config_model = ModuleUpdateConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ModuleUpdateConfig.model_validate(context.config)
        adapter = await resolve_adapter(context.session, tenant_id=context.tenant_id, module_key=config.module)
        if adapter is None:
            return Failure(f"unknown module {config.module!r}")

        resolved_id = resolve_template_value(config.item_id, context.variables)
        try:
            item_id = uuid.UUID(str(resolved_id))
        except ValueError:
            return Failure(f"item_id {resolved_id!r} is not a valid UUID")

        fields = interpolate_dict_values(config.fields, context.variables)
        try:
            item = await adapter.update(
                context.session, tenant_id=context.tenant_id, item_id=item_id, fields=fields
            )
        except NotImplementedError as exc:
            return Failure(str(exc))
        except (ValueError, ValidationError) as exc:
            return Failure(str(exc))

        if item is None:
            return Failure(f"{config.module} record {item_id} not found")
        return Success(output={"item": item})


node_executor_registry.register(ModuleUpdateExecutor())
