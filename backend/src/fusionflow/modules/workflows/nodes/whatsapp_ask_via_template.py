"""`whatsapp.ask_via_template` — sends a pre-approved template (HSM)
message, then pauses the run until this customer's next reply arrives,
exactly like `whatsapp.ask_question`/`whatsapp.ask_choice` do for a plain
session message (see `engine/run_loop.py`'s `Suspend`/`RunSuspended`/
`resume_run`).

Why this node exists alongside `whatsapp.send_template` (a one-shot,
non-suspending send): a workflow triggered by a non-WhatsApp event
(`order.created`, `payment.captured`, `manual.test_trigger`) has no
guaranteed open 24-hour customer service window, so its first outbound
WhatsApp message must be a template, not a session message
(`send_whatsapp_message`/`whatsapp.ask_choice`/`whatsapp.collect_text`/
`whatsapp.send_media`/`whatsapp.send_interactive_*` are all session-only —
see `whatsapp_send_media.py`'s own docstring for this established rule).
But sometimes that first business-initiated message also needs an answer
(e.g. "please rate your recent order 1-5") — `whatsapp.send_template` alone
can't wait for that reply. This node is the template-send equivalent of
`whatsapp.ask_question`'s pause/resume mechanic, so a template-initiated
conversation can still capture a reply, not just broadcast.

Template messages have no interactive/button component in this codebase
(`SendTemplateConfig`/`send_template_message` carry no button config), so
a reply to one is always free text — there is no interactive-tap variant
to branch on the way a *static*-source `whatsapp.ask_choice` can; this node
never registers a composite branch source (same as `whatsapp.collect_text`).

Once the customer replies here, WhatsApp's 24-hour session window is open
(any customer-initiated message opens/extends it) - everything *downstream*
of this node in the graph can safely go back to ordinary session-message
nodes.

Duplicates (rather than shares) `whatsapp_send_template.py`'s config shape
and local-template variable-count cross-check, per this codebase's
established "each node keeps its own private copy" convention for small
shared logic (see `orders_create_from_conversation.py`'s docstring, which
cites this same convention explicitly) rather than factoring out a shared
helper for two call sites.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select

from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
from fusionflow.modules.connectors.whatsapp.models import WhatsAppTemplate
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Suspend,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate
from fusionflow.modules.workflows.nodes._whatsapp_common import resolve_whatsapp_instance

_OUTPUT_SCHEMA = {
    # A resumed run wraps the customer's free-text reply as
    # `variables[node_id] = {"reply": answer}` (see `engine/run_loop.py`'s
    # `resume_run`) - same shape `whatsapp.ask_question`/`whatsapp.collect_text`
    # already document for their own suspending nodes.
    "type": "object",
    "properties": {"reply": {"type": "string"}},
}


class AskViaTemplateConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(
        min_length=1,
        description="The customer's WhatsApp number to send the template to. May reference the run context.",
        json_schema_extra={"format": "recipient"},
    )
    template_name: str = Field(min_length=1)
    language_code: str = Field(min_length=1, description="e.g. 'en_US' - must match the approved template exactly.")
    header_variable: str | None = Field(default=None, description="Only if the template's header has a {{1}} placeholder.")
    body_variables: list[str] = Field(default_factory=list, description="In order, one per {{n}} placeholder in the body.")


class AskViaTemplateExecutor(NodeExecutor):
    node_type = "whatsapp.ask_via_template"
    kind = "action"
    category = "Messages"
    subcategory = "Template"
    palette_group = "Talk to Customer"
    icon = "message-square-text"
    label = "Ask via WhatsApp Template"
    description = (
        "Sends a pre-approved template message, then pauses the run until this customer's next "
        "reply arrives - use this instead of 'Ask a Question' when the workflow wasn't triggered "
        "by an inbound WhatsApp message (e.g. order.created, payment.captured), since there's no "
        "guaranteed open 24-hour session to send a plain question through."
    )
    config_model = AskViaTemplateConfig
    output_schema = _OUTPUT_SCHEMA
    can_suspend = True
    # See whatsapp_ask_question.py's applicable_purposes comment - pausing
    # for one reply can't work inside a broadcast's flow.loop fan-out.
    applicable_purposes = ["automation"]
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = AskViaTemplateConfig.model_validate(context.config)
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
        return Suspend(correlation_key=to)

    async def extract_resume_value(self, config: dict[str, Any], resume_payload: dict[str, Any]) -> Any:
        # No interactive/button component on a template send in this
        # codebase - a reply is always free text.
        return resume_payload.get("text")


node_executor_registry.register(AskViaTemplateExecutor())
