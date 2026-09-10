"""`data.transform` — derives/reshapes data mid-flow from the running
variable context, with zero new node code ever needed for a new
derivation: `outputs` is a plain `{name: template}` map, each value a
`{{dot.path}}` (or literal) template resolved the same way every other
node's templated fields are. The completion of Part D's generic-executor
set alongside `connector.action`/`http.request`/`condition.multi_branch`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import resolve_template_value


class DataTransformConfig(BaseModel):
    outputs: dict[str, str] = Field(
        min_length=1,
        description="Each value is a '{{dot.path}}' template (or literal string) resolved against the run context.",
    )


class DataTransformExecutor(NodeExecutor):
    node_type = "data.transform"
    kind = "action"
    category = "Data"
    label = "Transform Data"
    description = "Derives new named values from the running context - no code needed for a new derivation."
    config_model = DataTransformConfig

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = DataTransformConfig.model_validate(context.config)
        output: dict[str, Any] = {
            name: resolve_template_value(template, context.variables) for name, template in config.outputs.items()
        }
        return Success(output=output)


node_executor_registry.register(DataTransformExecutor())
