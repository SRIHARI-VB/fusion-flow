"""`whatsapp.ask_for_cart` — shows the customer a WhatsApp Commerce
Catalog product list (real multi-select: add any number of items to a
cart, submit it as one message) and pauses the run until they submit it,
same pause/resume mechanic as `whatsapp.ask_choice`/`whatsapp.ask_question`.

Always module-sourced (never a hand-typed static option list, unlike
`whatsapp.ask_choice`) - the whole point is showing many real catalog
records, not a small hand-authored set. Requires the tenant's WhatsApp
Business Account to already have a Meta Commerce Catalog connected
(external, Meta-side setup this codebase doesn't manage) and each shown
product's `retailer_id` (configured on Meta's side) to equal that
product's own id in this system (see
`WhatsAppAdapter.send_product_list_message`'s docstring for why - no
separate id-mapping table exists or is planned).

Not a composite-branch source: an arbitrary cart's contents are never a
compile-time-knowable, small enumerable option set the way
`whatsapp.ask_choice`'s static options are - a workflow reads the whole
submitted cart via `{{this_node.reply.product_items}}` and hands it to
`orders.create_from_cart`, which does its own per-item lookup/validation
in real Python code, not by branching per possible cart shape.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
from fusionflow.modules.workflows.engine.module_registry import interpolate_dict_values, resolve_adapter
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
    "type": "object",
    "properties": {
        "reply": {
            "type": "object",
            "properties": {
                "catalog_id": {"type": "string"},
                "product_items": {"type": "array"},
                "note": {"type": "string"},
            },
        }
    },
}


class AskForCartConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(
        min_length=1, description="Recipient wa_id, typically {{trigger.from}}. Also the suspend's correlation key."
    )
    catalog_id: str = Field(
        min_length=1, description="Meta Commerce Catalog id connected to this WhatsApp Business Account."
    )
    body_text: str = Field(min_length=1, json_schema_extra={"format": "textarea"})
    footer_text: str | None = None
    module: str = Field(min_length=1, description="A module key from GET /workflows/modules - e.g. 'products'.")
    filters: dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(default=30, ge=1, le=30, description="Meta's own cap: up to 30 product items across all sections.")
    section_title: str = Field(default="Products")


class AskForCartExecutor(NodeExecutor):
    node_type = "whatsapp.ask_for_cart"
    kind = "action"
    category = "Messages"
    subcategory = "Catalog"
    palette_group = "Talk to Customer"
    icon = "shopping-cart"
    label = "Ask Customer to Build a Cart"
    description = (
        "Shows a WhatsApp catalog of products the customer can add several of to a cart, then pauses "
        "until they submit it - the only way to let a customer pick more than one item in one step."
    )
    config_model = AskForCartConfig
    output_schema = _OUTPUT_SCHEMA
    can_suspend = True
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = AskForCartConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)
        catalog_id = interpolate(config.catalog_id, context.variables)
        body_text = interpolate(config.body_text, context.variables)
        footer_text = interpolate(config.footer_text, context.variables) if config.footer_text else None

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        adapter = await resolve_adapter(context.session, tenant_id=context.tenant_id, module_key=config.module)
        if adapter is None:
            return Failure(f"unknown module {config.module!r}")
        filters = interpolate_dict_values(config.filters, context.variables)
        rows = await adapter.list(context.session, tenant_id=context.tenant_id, filters=filters, limit=config.limit)

        sections = [
            {
                "title": config.section_title[:24],
                "product_items": [{"product_retailer_id": str(row.get("id"))} for row in rows],
            }
        ]

        await whatsapp_adapter.send_product_list_message(
            instance=instance,
            to=to,
            catalog_id=catalog_id,
            body_text=body_text,
            sections=sections,
            footer_text=footer_text,
            session=context.session,
        )

        return Suspend(correlation_key=to)

    async def extract_resume_value(self, config: dict[str, Any], resume_payload: dict[str, Any]) -> Any:
        # `None` when the customer replied with something other than
        # submitting a cart (free text, a stray tap, ...) - a legitimate
        # outcome the workflow author's downstream nodes see as an absent
        # `{{this_node.reply}}`, not something this node itself guards
        # against (see `orders.create_from_cart`'s own empty-cart check).
        return resume_payload.get("order")


node_executor_registry.register(AskForCartExecutor())
