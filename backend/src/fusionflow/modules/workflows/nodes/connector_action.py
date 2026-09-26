"""`connector.action` — a single generic node type that dispatches to any
connector adapter's `perform_action(action, params)` hook
(`modules/connectors/base.py::ConnectorAdapter.perform_action`).

This is the first half of Part D's "catalog/config, not code" answer to
"how do we add a new integration capability without touching the
engine": adding a brand-new WhatsApp capability (or a whole new adapter's
capability) needs one `elif action == "..."` branch inside that adapter's
own `perform_action` override - never a new `NodeExecutor` subclass, never
a change to this file, never a workflow-engine registry change. The
second half is the `WorkflowNodeTemplate` admin catalog (see
`modules/admin/models.py`), which lets that capability get its own
friendly palette entry (icon, label, pre-filled `action`/config) as pure
admin data entry - no deploy.

`params` values may reference the running variable context via the same
`{{dot.path}}` templating every other node/adapter call already uses
(`fusionflow.modules.workflows.engine.templating`).
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import registry as connector_registry
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import resolve_template_value_deep


class ConnectorActionConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    action: str = Field(min_length=1, description="Which action to run on the connected integration, e.g. 'send_text_message'.")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "The settings for that action. String values may use '{{dot.path}}' templating - "
            "including strings nested inside lists/dicts, e.g. a button template's "
            "buttons[].payload."
        ),
    )


def _interpolate_params(params: dict[str, Any], variables: dict[str, Any]) -> dict[str, Any]:
    return {key: resolve_template_value_deep(value, variables) for key, value in params.items()}


class ConnectorActionExecutor(NodeExecutor):
    node_type = "connector.action"
    kind = "action"
    category = "Integrations"
    label = "Connector Action"
    description = (
        "Calls a named action on a connected connector instance (e.g. send a WhatsApp message). "
        "The specific action set depends on the connector."
    )
    config_model = ConnectorActionConfig
    # A real outbound provider call - the same retry rationale as
    # send_whatsapp_message.py's dedicated node, which this generic
    # executor is meant to eventually replace via a WorkflowNodeTemplate
    # (see Part E's proof-of-concept).
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ConnectorActionConfig.model_validate(context.config)

        try:
            connector_instance_id = uuid.UUID(config.connector_instance_id)
        except ValueError:
            return Failure(f"connector_instance_id {config.connector_instance_id!r} is not a valid UUID")

        instance = await connector_service.get_instance(
            context.session, tenant_id=context.tenant_id, instance_id=connector_instance_id
        )
        if instance is None:
            return Failure(f"connector instance {connector_instance_id} not found for this tenant")

        adapter = connector_registry.get_or_none(instance.connector_type.key)
        if adapter is None:
            return Failure(f"no adapter registered for connector instance {connector_instance_id}")

        params = _interpolate_params(config.params, context.variables)

        # A genuinely unknown action is a config error (Failure, not
        # retried); anything else the adapter's own outbound call raises
        # propagates so this node's `retryable` setting applies to it.
        try:
            output = await adapter.perform_action(
                action=config.action, params=params, instance=instance, session=context.session
            )
        except NotImplementedError as exc:
            return Failure(str(exc))

        return Success(output=output)


node_executor_registry.register(ConnectorActionExecutor())
