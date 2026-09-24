"""`connectors.is_connected` — "does this tenant currently have an
active, usable instance of connector type X" as a plain boolean, so a
workflow can gate a UI choice on actual capability instead of always
offering it (e.g. only ask "online or offline meeting" when this
tenant's `google_meet` connector is actually connected, rather than
asking and then failing the follow-up `connector.action` call).

Deliberately generic over `connector_type_key` (a config field, not a
fixed `required_connector_type_key` on the executor class) - unlike
`instagram.find_or_create_customer`'s hardcoded `"customers"`, this
node's whole point is to be usable for *any* connector type key a
workflow author names, including one this tenant has never connected at
all. A tenant with zero instances of that type, or no `ConnectorType`
row for that key at all, is not an error here - both just resolve to
`{"connected": False}`, the same "missing is a normal negative, not a
5xx" reasoning `record_get_latest.py` applies to "no matching row."

"Connected and usable" means `ConnectorInstance.state ==
ConnectorState.CONNECTED` specifically - `connectors/models.py`'s fixed
lifecycle (`not_connected -> connecting -> connected ->
action_required -> error -> disconnected`, with `error`/
`action_required` looping back to `connecting` via reconnect) means an
instance can exist in a not-yet-finished or degraded state; only
`connected` is what every adapter's own `perform_action` call assumes
before it will actually work, so this node holds this node's
`connectors.service.list_instances` result to that one state rather
than "any instance row exists at all."
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.models import ConnectorState
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "connected": {
            "type": "boolean",
            "description": "True iff this tenant has a connector instance of connector_type_key in state 'connected'.",
        },
    },
}


class IsConnectedConfig(BaseModel):
    connector_type_key: str = Field(
        min_length=1,
        description="The connector type's key to check, e.g. 'google_meet' or 'instagram'.",
    )


class IsConnectedExecutor(NodeExecutor):
    node_type = "connectors.is_connected"
    kind = "action"
    category = "Integrations"
    label = "Connector Is Connected"
    description = (
        "Checks whether this tenant currently has an active, connected instance of a given connector "
        "type - use this to conditionally offer a capability only when it's actually available."
    )
    config_model = IsConnectedConfig
    output_schema = _OUTPUT_SCHEMA
    # Purpose-agnostic infrastructure, same bucket as `connector.action`/
    # `http.request`/`flow.loop` - `applicable_purposes` stays the default
    # `None` (usable from either an automation or a broadcast loop) rather
    # than an explicit tag, per `tests/test_broadcast_scheduling.py`'s
    # closed allowlist of what actually needs one.
    # A plain read against already-loaded tenant data - no outbound call,
    # nothing to retry, same as record_get_latest.py's reasoning.
    retryable = False

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = IsConnectedConfig.model_validate(context.config)

        instances = await connector_service.list_instances(context.session, context.tenant_id)
        connected = any(
            instance.connector_type.key == config.connector_type_key
            and instance.state == ConnectorState.CONNECTED
            for instance in instances
        )
        return Success(output={"connected": connected})


node_executor_registry.register(IsConnectedExecutor())
