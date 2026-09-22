"""`instagram.postback_received` — fires when someone taps a button-template
or ice-breaker button sent by a connected Instagram account. Delivered as
`messaging[].postback` on the Messaging webhook
(`modules/connectors/instagram/adapter.py::_extract_postback`).

Same thin-echo-trigger shape as `instagram_message_received.py`.
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

NODE_TYPE = "instagram.postback_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "payload": {"type": "string"},
        "title": {"type": "string"},
    },
}


class InstagramPostbackReceivedConfig(BaseModel):
    """No required fields — which connector instance fired is implicit in
    which `workflow_triggers` row matched the inbox event, not baked into
    the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class InstagramPostbackReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "Instagram Button Tapped"
    description = (
        "Fires when someone taps a button-template or ice-breaker button sent by a connected "
        "Instagram account. Run context is seeded with the tapper's Instagram-scoped id "
        "('from'), the button's payload string, and its title."
    )
    config_model = InstagramPostbackReceivedConfig
    required_connector_type_key = "instagram"
    output_schema = _OUTPUT_SCHEMA
    applicable_purposes = ["automation"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = InstagramPostbackReceivedExecutor()
node_executor_registry.register(_executor)
trigger_registry.register(
    TriggerDefinition(
        trigger_type=_executor.node_type,
        category=_executor.category,
        label=_executor.label,
        description=_executor.description,
        config_model=_executor.config_model,
        required_connector_type_key=_executor.required_connector_type_key,
        output_schema=_executor.output_schema,
        applicable_purposes=_executor.applicable_purposes,
    )
)
