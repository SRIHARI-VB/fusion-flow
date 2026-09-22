"""`instagram.referral_received` — fires when a conversation starts (or a
first message carries) a referral from an ad or an ig.me shortlink.
Delivered as `messaging[].referral` (or `messaging[].postback.referral`) on
the Messaging webhook
(`modules/connectors/instagram/adapter.py::_extract_referral`).

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

NODE_TYPE = "instagram.referral_received"

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "from": {"type": "string"},
        "ref": {"type": "string"},
        "source": {"type": "string"},
        "ad_id": {"type": "string"},
    },
}


class InstagramReferralReceivedConfig(BaseModel):
    """No required fields — which connector instance fired is implicit in
    which `workflow_triggers` row matched the inbox event, not baked into
    the node's static config."""

    description: str | None = Field(default=None, max_length=200)


class InstagramReferralReceivedExecutor(NodeExecutor):
    node_type = NODE_TYPE
    kind = "trigger"
    category = "Messages"
    label = "Instagram Ad/Link Referral Received"
    description = (
        "Fires when a user starts (or continues) a conversation via an ad click or an ig.me "
        "shortlink. Run context is seeded with the sender's Instagram-scoped id ('from'), the "
        "referral's 'ref' value, its source ('ADS' or 'SHORTLINK'), and the ad id when present."
    )
    config_model = InstagramReferralReceivedConfig
    required_connector_type_key = "instagram"
    output_schema = _OUTPUT_SCHEMA
    applicable_purposes = ["automation"]

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Success(output=dict(context.variables.get("trigger", {})))


_executor = InstagramReferralReceivedExecutor()
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
