"""`whatsapp.collect_text` — a friendly, text-only front door onto
`whatsapp.ask_question` (send a question, pause until the customer's next
reply): a non-technical author picking "collect a delivery address" or
"ask for their name" from the palette shouldn't have to first pick
`input_type="text"` out of a dropdown that also offers `buttons`/`list`
options this node has no use for. Delegates the actual send+suspend logic
to `AskQuestionExecutor` unchanged (translating this node's own smaller
config into `whatsapp.ask_question`'s shape) rather than duplicating it.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.registry import ExecutionContext, NodeExecutor, NodeResult, node_executor_registry
from fusionflow.modules.workflows.nodes.whatsapp_ask_question import AskQuestionExecutor


class CollectTextConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(
        min_length=1, description="Recipient wa_id, typically {{trigger.from}}. Also the suspend's correlation key."
    )
    question: str = Field(
        min_length=1,
        description="The question's body text, e.g. 'What's your delivery address?'",
        json_schema_extra={"format": "textarea"},
    )


_OUTPUT_SCHEMA = {"type": "object", "properties": {"reply": {"type": "string"}}}

_ask_question_executor = AskQuestionExecutor()


class CollectTextExecutor(NodeExecutor):
    node_type = "whatsapp.collect_text"
    kind = "action"
    category = "Messages"
    subcategory = "Ask"
    palette_group = "Talk to Customer"
    icon = "message-square-text"
    label = "Ask for Information"
    description = "Asks a free-text question (name, address, notes, ...) and pauses until the customer replies."
    config_model = CollectTextConfig
    output_schema = _OUTPUT_SCHEMA
    can_suspend = True
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = CollectTextConfig.model_validate(context.config)
        translated_context = dataclasses.replace(
            context,
            config={
                "connector_instance_id": config.connector_instance_id,
                "to": config.to,
                "input_type": "text",
                "question": config.question,
            },
        )
        return await _ask_question_executor.execute(translated_context)

    async def extract_resume_value(self, config: dict[str, Any], resume_payload: dict[str, Any]) -> Any:
        # `run_loop.py::resume_run` wraps whatever this returns as
        # `variables[node_id] = {"reply": answer}` itself (not this node) -
        # returning the raw text directly here is what makes
        # `{{this_node.reply}}` a plain string downstream, matching
        # `output_schema` above.
        return resume_payload.get("text")


node_executor_registry.register(CollectTextExecutor())
