"""`whatsapp.send_interactive_list` — sends an outbound session message
with a tap-to-open list of up to 10 selectable rows (across all sections)
through a connected WhatsApp connector instance
(`modules/connectors/whatsapp/adapter.py::WhatsAppAdapter.send_interactive_message`).

A customer's selection fires `whatsapp.interactive_reply_received` with
`interactive.id` matching whichever row's `id` they picked.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
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


class ListRow(BaseModel):
    id: str = Field(min_length=1, description="Echoed back in interactive.id when the customer picks this row.")
    title: str = Field(min_length=1, max_length=24)
    description: str | None = Field(default=None, max_length=72)


class ListSection(BaseModel):
    title: str = Field(min_length=1, max_length=24)
    rows: list[ListRow] = Field(min_length=1)


class SendInteractiveListConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(min_length=1, description="Recipient wa_id. May reference the run context.")
    body_text: str = Field(min_length=1)
    list_button_label: str = Field(min_length=1, max_length=20, default="Choose")
    sections: list[ListSection] = Field(min_length=1)

    @model_validator(mode="after")
    def _limit_total_rows(self) -> "SendInteractiveListConfig":
        total_rows = sum(len(s.rows) for s in self.sections)
        if total_rows > 10:
            raise ValueError(f"Meta allows at most 10 rows total across all sections, got {total_rows}")
        return self


class SendInteractiveListExecutor(NodeExecutor):
    node_type = "whatsapp.send_interactive_list"
    kind = "action"
    category = "Choices"
    subcategory = "List"
    label = "Send WhatsApp List"
    description = "Sends a tap-to-open list of up to 10 rows; a selection fires whatsapp.interactive_reply_received."
    config_model = SendInteractiveListConfig
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = SendInteractiveListConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)
        body_text = interpolate(config.body_text, context.variables)

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        sections_payload = [
            {
                "title": section.title,
                "rows": [{"id": r.id, "title": r.title, "description": r.description} for r in section.rows],
            }
            for section in config.sections
        ]
        await whatsapp_adapter.send_interactive_message(
            instance=instance,
            to=to,
            body_text=body_text,
            interactive_type="list",
            list_button_label=config.list_button_label,
            sections=sections_payload,
            session=context.session,
        )
        return Success(output={"to": to, "section_count": len(config.sections)})


node_executor_registry.register(SendInteractiveListExecutor())
