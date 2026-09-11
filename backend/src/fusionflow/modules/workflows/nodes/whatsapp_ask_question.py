"""`whatsapp.ask_question` — sends a question (free text, up to 3 quick-
reply buttons, or a tap-to-open list) through a connected WhatsApp
connector instance and then suspends the run (Phase 8 Part A pause/resume)
until this same customer's next reply arrives on the same channel. The
"one at a time" building block for a multi-turn conversational workflow
(size, then shipping address, then color, ...) — see `engine/run_loop.py`'s
`Suspend`/`RunSuspended`/`resume_run`.

Sends via the same adapter calls as `send_whatsapp_message.py`/
`whatsapp_send_interactive_buttons.py`/`whatsapp_send_interactive_list.py`;
`buttons`/`sections` reuse those two node types' own config row shapes
(`ButtonEntry`/`ListSection`) so an author reuses a familiar field
vocabulary here rather than a new one. Both fields are shown unconditionally
regardless of `input_type` (no conditional-field UI infrastructure needed
this phase) — an author simply ignores whichever doesn't apply to their
chosen `input_type`.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
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
from fusionflow.modules.workflows.nodes.whatsapp_send_interactive_buttons import ButtonEntry
from fusionflow.modules.workflows.nodes.whatsapp_send_interactive_list import ListSection


class AskQuestionConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(
        min_length=1,
        description="Recipient wa_id, typically {{trigger.from}}. Also becomes the suspend's correlation key.",
    )
    input_type: Literal["text", "buttons", "list"]
    question: str = Field(
        min_length=1, description="The question's body text.", json_schema_extra={"format": "textarea"}
    )
    buttons: list[ButtonEntry] | None = Field(
        default=None, description="Only meaningful when input_type='buttons' (up to 3, per Meta's own limit)."
    )
    sections: list[ListSection] | None = Field(
        default=None, description="Only meaningful when input_type='list' (up to 10 rows total)."
    )


class AskQuestionExecutor(NodeExecutor):
    node_type = "whatsapp.ask_question"
    kind = "action"
    category = "Messages"
    subcategory = "Ask"
    label = "Ask a Question"
    description = "Sends a question, then pauses the run until this customer's next reply arrives."
    config_model = AskQuestionConfig
    can_suspend = True
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = AskQuestionConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)
        question = interpolate(config.question, context.variables)

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        if config.input_type == "text":
            await whatsapp_adapter.send_text_message(
                instance=instance, to=to, body=question, session=context.session
            )
        else:
            buttons_payload = (
                [{"id": b.id, "title": b.title} for b in config.buttons] if config.buttons else None
            )
            sections_payload = (
                [
                    {
                        "title": section.title,
                        "rows": [
                            {"id": r.id, "title": r.title, "description": r.description} for r in section.rows
                        ],
                    }
                    for section in config.sections
                ]
                if config.sections
                else None
            )
            await whatsapp_adapter.send_interactive_message(
                instance=instance,
                to=to,
                body_text=question,
                interactive_type="button" if config.input_type == "buttons" else "list",
                buttons=buttons_payload,
                sections=sections_payload,
                session=context.session,
            )

        return Suspend(correlation_key=to)

    async def extract_resume_value(self, config: dict[str, Any], resume_payload: dict[str, Any]) -> Any:
        parsed = AskQuestionConfig.model_validate(config)
        if parsed.input_type == "text":
            return resume_payload.get("text")
        return (resume_payload.get("interactive") or {}).get("id")


node_executor_registry.register(AskQuestionExecutor())
