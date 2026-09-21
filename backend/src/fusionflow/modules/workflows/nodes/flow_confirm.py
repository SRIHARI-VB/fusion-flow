"""`flow.confirm` — a friendly "ask a yes/no question" shortcut: sends two
fixed WhatsApp quick-reply buttons ("Yes"/"No") and pauses until the
customer answers, normalizing common free-text replies ("yeah", "nope",
...) the same way a tap would resolve. Functionally a fixed-shape special
case of `whatsapp.ask_choice` (see that module's docstring for why
branching-on-the-answer is a compile-time-synthesized downstream
`condition.multi_branch` node, not something this node does itself) - kept
as its own node type rather than a preset `whatsapp.ask_choice` config
because "yes/no confirm" is common enough, and simple enough, to deserve
its own unmistakable palette entry for a non-technical author (no
`source`/module-vs-static choice to make at all).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
from fusionflow.modules.workflows.engine.composite_branching import register_composite_branch_source
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

_YES_SYNONYMS = {"y", "yes", "yeah", "yep", "sure", "ok", "okay"}
_NO_SYNONYMS = {"n", "no", "nope", "cancel"}

#: The confirm node's branch shape never varies - always exactly these two
#: options, regardless of config (unlike `whatsapp.ask_choice`, whose
#: static branch source reads its options from config).
_OPTIONS = [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]


class ConfirmConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(
        min_length=1,
        description="The customer's WhatsApp number to send the question to (usually {{trigger.from}}).",
        json_schema_extra={"format": "recipient"},
    )
    question: str = Field(min_length=1, json_schema_extra={"format": "textarea"})


_OUTPUT_SCHEMA = {"type": "object", "properties": {"reply": {"type": "object", "properties": {"id": {"type": "string"}}}}}


class ConfirmExecutor(NodeExecutor):
    node_type = "flow.confirm"
    kind = "action"
    category = "Flow Control"
    palette_group = "Talk to Customer"
    icon = "check-circle"
    label = "Ask Yes / No"
    description = "Asks a yes/no question and pauses until the customer answers."
    config_model = ConfirmConfig
    output_schema = _OUTPUT_SCHEMA
    can_suspend = True
    # See whatsapp_ask_question.py's applicable_purposes comment - pausing
    # for one reply can't work inside a broadcast's flow.loop fan-out.
    applicable_purposes = ["automation"]
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ConfirmConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)
        question = interpolate(config.question, context.variables)

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        await whatsapp_adapter.send_interactive_message(
            instance=instance,
            to=to,
            body_text=question,
            interactive_type="button",
            buttons=[{"id": opt["id"], "title": opt["label"]} for opt in _OPTIONS],
            session=context.session,
        )
        return Suspend(correlation_key=to)

    async def extract_resume_value(self, config: dict[str, Any], resume_payload: dict[str, Any]) -> Any:
        interactive = resume_payload.get("interactive") or {}
        tapped_id = interactive.get("id")
        if tapped_id in ("yes", "no"):
            return {"id": tapped_id}

        text = (resume_payload.get("text") or "").strip().lower()
        if text in _YES_SYNONYMS:
            return {"id": "yes"}
        if text in _NO_SYNONYMS:
            return {"id": "no"}
        # Neither a recognized tap nor a recognized free-text synonym - the
        # synthesized branch node's optional "default" handle absorbs this
        # (see condition_multi_branch.py's declared_optional_output_handles).
        return {"id": None}


def _static_options(config: dict[str, Any]) -> list[dict[str, str]] | None:
    return list(_OPTIONS)


register_composite_branch_source("flow.confirm", _static_options)
node_executor_registry.register(ConfirmExecutor())
