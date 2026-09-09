"""`manual.test_trigger` — fires immediately with an arbitrary JSON payload.

Fully self-contained: no other module needed. This is the trigger
`POST /workflows/{id}/simulate` uses for its synchronous dry run (bypassing
the inbox entirely), and is registered in both registries — `trigger_registry`
(so it shows up in the Triggers palette category) and
`node_executor_registry` (so the run loop can execute it like any other
graph node: its "execution" is simply seeding the run's variable context
with whatever payload the caller passed at run-creation time).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    TriggerDefinition,
    node_executor_registry,
    trigger_registry,
)

NODE_TYPE = "manual.test_trigger"


class ManualTestTriggerConfig(BaseModel):
    """No required fields — the test payload is supplied per-run (via
    simulate), not baked into the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class ManualTestTriggerExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Triggers"
    label = "Manual Test Trigger"
    description = (
        "Fires immediately with a caller-supplied JSON payload. Used by the "
        "simulate endpoint for dry runs; never dispatched from the inbox."
    )
    config_model = ManualTestTriggerConfig

    async def execute(self, context: ExecutionContext) -> NodeResult:
        # By the time the run loop reaches this node the run already
        # exists *because* this trigger fired — `variables["trigger"]` was
        # seeded by run_loop.execute_run from the caller-supplied payload.
        # This step's own output just mirrors that for the run trace.
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = ManualTestTriggerExecutor()
node_executor_registry.register(_executor)
trigger_registry.register(
    TriggerDefinition(
        trigger_type=_executor.node_type,
        category=_executor.category,
        label=_executor.label,
        description=_executor.description,
        config_model=_executor.config_model,
    )
)
