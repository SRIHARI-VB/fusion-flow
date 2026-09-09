"""`log.noop` — records its input (the running variable context) as its
output, verbatim. No side effects, no external dependency: exists so a
chain of nodes can be built and tested end-to-end before any real
action/connector node type exists."""

from __future__ import annotations

from pydantic import BaseModel

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)


class LogNoopConfig(BaseModel):
    message: str | None = None


class LogNoopExecutor(NodeExecutor):
    node_type = "log.noop"
    kind = "action"
    category = "Actions"
    label = "Log (No-Op)"
    description = (
        "Records the current run context as its output and does nothing else. "
        "Useful for building/testing a workflow chain in isolation."
    )
    config_model = LogNoopConfig

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(
            output={"message": context.config.get("message"), "context": dict(context.variables)}
        )


node_executor_registry.register(LogNoopExecutor())
