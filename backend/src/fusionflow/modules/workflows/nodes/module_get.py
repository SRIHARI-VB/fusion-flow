"""`module.get` — generic node type: fetch a single row from any fixed
module by id through its registered `ModuleQueryAdapter`."""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.module_registry import resolve_adapter
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


class ModuleGetConfig(BaseModel):
    module: str = Field(min_length=1, description="Catalog module key, e.g. 'products', 'customers'.")
    item_id: str = Field(min_length=1, description="Row id. May use '{{dot.path}}' templating.")


class ModuleGetExecutor(NodeExecutor):
    node_type = "module.get"
    kind = "action"
    category = "Data"
    label = "Get Module Record"
    description = "Fetches a single row from a fixed module by id."
    config_model = ModuleGetConfig
    output_schema = _OUTPUT_SCHEMA

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ModuleGetConfig.model_validate(context.config)
        adapter = await resolve_adapter(context.session, tenant_id=context.tenant_id, module_key=config.module)
        if adapter is None:
            return Failure(f"unknown module {config.module!r}")

        resolved_id = resolve_template_value(config.item_id, context.variables)
        try:
            item_id = uuid.UUID(str(resolved_id))
        except ValueError:
            return Failure(f"item_id {resolved_id!r} is not a valid UUID")

        item = await adapter.get(context.session, tenant_id=context.tenant_id, item_id=item_id)
        if item is None:
            return Failure(f"{config.module} record {item_id} not found")
        return Success(output={"item": item})


node_executor_registry.register(ModuleGetExecutor())
