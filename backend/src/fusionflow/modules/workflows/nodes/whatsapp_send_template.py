"""`whatsapp.send_template` — sends a pre-approved template (HSM) message
through a connected WhatsApp connector instance
(`modules/connectors/whatsapp/adapter.py::WhatsAppAdapter.send_template_message`).

The only message kind sendable outside the 24-hour customer service
window, and the only kind Meta requires pre-approval for
(marketing/utility/authentication - see
`modules/connectors/whatsapp/models.py::WhatsAppTemplate`). `category` is
never a field here - it's a property of the template itself, informational
for the picker UI a template was chosen from, not a send-time parameter.

If a matching row exists in the local `WhatsAppTemplate` catalog (synced
from Meta or entered manually), this node cross-checks the supplied
`body_variables` count against the template's own recorded
`variable_count` and fails clean *before* calling Meta if they don't
match - catching an off-by-one before it becomes a live API rejection.
No local record (not yet synced/registered) simply skips that check and
attempts the send as configured, letting Meta be the final source of
truth per this codebase's established convention.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from sqlalchemy import select

from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
from fusionflow.modules.connectors.whatsapp.models import WhatsAppTemplate
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate
from fusionflow.modules.workflows.nodes._whatsapp_common import resolve_whatsapp_instance


class SendTemplateConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(min_length=1, description="Recipient wa_id. May reference the run context.")
    template_name: str = Field(min_length=1)
    language_code: str = Field(min_length=1, description="e.g. 'en_US' - must match the approved template exactly.")
    header_variable: str | None = Field(default=None, description="Only if the template's header has a {{1}} placeholder.")
    body_variables: list[str] = Field(default_factory=list, description="In order, one per {{n}} placeholder in the body.")


class SendTemplateExecutor(NodeExecutor):
    node_type = "whatsapp.send_template"
    kind = "action"
    category = "Messages"
    subcategory = "Template"
    label = "Send WhatsApp Template"
    description = "Sends a pre-approved marketing/utility/authentication template message, deliverable even outside the 24-hour session window."
    config_model = SendTemplateConfig
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = SendTemplateConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)
        header_variable = interpolate(config.header_variable, context.variables) if config.header_variable else None
        body_variables = [interpolate(v, context.variables) for v in config.body_variables]

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        local_template = (
            await context.session.execute(
                select(WhatsAppTemplate).where(
                    WhatsAppTemplate.connector_instance_id == instance.id,
                    WhatsAppTemplate.name == config.template_name,
                    WhatsAppTemplate.language == config.language_code,
                )
            )
        ).scalar_one_or_none()
        if local_template is not None:
            expected_count = (local_template.components.get("body") or {}).get("variable_count")
            if expected_count is not None and expected_count != len(body_variables):
                return Failure(
                    f"template {config.template_name!r} ({config.language_code}) expects "
                    f"{expected_count} body variable(s), got {len(body_variables)}"
                )

        await whatsapp_adapter.send_template_message(
            instance=instance,
            to=to,
            template_name=config.template_name,
            language_code=config.language_code,
            header_variable=header_variable,
            body_variables=body_variables,
            session=context.session,
        )
        return Success(output={"to": to, "template_name": config.template_name})


node_executor_registry.register(SendTemplateExecutor())
