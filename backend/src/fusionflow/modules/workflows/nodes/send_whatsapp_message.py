"""`send_whatsapp_message` — sends an outbound WhatsApp text message through
a connected WhatsApp connector instance
(`modules/connectors/whatsapp/adapter.py::WhatsAppAdapter.send_text_message`).

`to`/`body` support simple `{{dot.path}}` interpolation against the running
variable context (trigger payload + prior node outputs) — the same
dot-path addressing `condition.field_compare` already established for
reading context values (see its `_resolve_path` helper); this node just
also supports embedding those values inside a literal string, rather than
inventing a new templating syntax.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)

_TEMPLATE_RE = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def _resolve_path(data: dict[str, Any], path: str) -> Any:
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _interpolate(template: str, variables: dict[str, Any]) -> str:
    """Replace every `{{dot.path}}` occurrence in `template` with the
    resolved value from `variables` (stringified), or '' if unresolved."""

    def _replace(match: "re.Match[str]") -> str:
        value = _resolve_path(variables, match.group(1))
        return "" if value is None else str(value)

    return _TEMPLATE_RE.sub(_replace, template)


class SendWhatsAppMessageConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(
        min_length=1,
        description="Recipient wa_id. May reference the run context, e.g. '{{trigger.from}}'.",
    )
    body: str = Field(
        min_length=1,
        description="Message text. May reference the run context, e.g. 'Thanks {{trigger.from}}!'.",
        json_schema_extra={"format": "textarea"},
    )


class SendWhatsAppMessageExecutor(NodeExecutor):
    node_type = "send_whatsapp_message"
    kind = "action"
    category = "Messages"
    label = "Send WhatsApp Message"
    description = (
        "Sends an outbound WhatsApp text message through a connected WhatsApp "
        "connector instance."
    )
    config_model = SendWhatsAppMessageConfig
    required_connector_type_key = "whatsapp"
    # This node makes a real outbound network call (the WhatsApp Cloud
    # API) - a flaky/slow response is exactly the transient-failure class
    # run_loop.py's retry-with-backoff exists for. The adapter call below
    # is deliberately left un-caught (unlike a plain config/lookup error,
    # which stays a clean `Failure`) so a transient exception propagates
    # to run_loop and gets retried instead of being silently swallowed
    # into a single, permanent `Failure` before retry logic ever sees it.
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = SendWhatsAppMessageConfig.model_validate(context.config)
        to = _interpolate(config.to, context.variables)
        body = _interpolate(config.body, context.variables)

        try:
            connector_instance_id = uuid.UUID(config.connector_instance_id)
        except ValueError:
            return Failure(f"connector_instance_id {config.connector_instance_id!r} is not a valid UUID")

        instance = await connector_service.get_instance(
            context.session, tenant_id=context.tenant_id, instance_id=connector_instance_id
        )
        if instance is None:
            return Failure(f"connector instance {connector_instance_id} not found for this tenant")

        await whatsapp_adapter.send_text_message(
            instance=instance, to=to, body=body, session=context.session
        )

        return Success(output={"to": to, "body": body})


node_executor_registry.register(SendWhatsAppMessageExecutor())
