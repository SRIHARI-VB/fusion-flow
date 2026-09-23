"""`instagram.find_or_create_customer` — the bridge between an Instagram
automation and the Customers module: looks up a `Customer` by
`external_ref` (typically `{{trigger.from}}`, the sender's Instagram-
scoped id), creating one if none exists.

Sibling of `whatsapp.find_or_create_customer` (that one keys off `phone`,
the natural bridge for a channel with no phone number). Not an Instagram
API call at all - a plain Customers-module operation keyed off an
Instagram payload field.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fusionflow.modules.customers import service as customers_service
from fusionflow.modules.customers.schemas import CustomerCreate, CustomerOut
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "customer": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "external_ref": {"type": "string"},
                "created_at": {"type": "string"},
            },
        },
        "created": {"type": "boolean"},
    },
}


class FindOrCreateCustomerConfig(BaseModel):
    external_ref: str = Field(
        min_length=1,
        description="The Instagram-scoped sender id, typically '{{trigger.from}}'.",
        json_schema_extra={"format": "recipient"},
    )
    name: str | None = Field(
        default=None, description="Fallback name to use if a new customer must be created."
    )


class InstagramFindOrCreateCustomerExecutor(NodeExecutor):
    node_type = "instagram.find_or_create_customer"
    kind = "action"
    category = "Messages"
    subcategory = "Contact"
    label = "Find or Create Customer by Instagram Id"
    description = "Looks up a Customer by Instagram-scoped id (e.g. the DM sender), creating one if none exists."
    config_model = FindOrCreateCustomerConfig
    required_connector_type_key = "customers"
    # Account/CRM utility, not conversation content - matches
    # `whatsapp.find_or_create_customer`'s identical grouping choice.
    palette_group = "Advanced"
    applicable_purposes = ["automation", "broadcast"]
    output_schema = _OUTPUT_SCHEMA
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = FindOrCreateCustomerConfig.model_validate(context.config)
        external_ref = interpolate(config.external_ref, context.variables)
        name = interpolate(config.name, context.variables) if config.name else None

        existing = await customers_service.get_customer_by_external_ref(context.session, context.tenant_id, external_ref)
        if existing is not None:
            return Success(output={"customer": CustomerOut.model_validate(existing).model_dump(mode="json"), "created": False})

        created = await customers_service.create_customer(
            context.session,
            context.tenant_id,
            CustomerCreate(name=name or f"Instagram: {external_ref}", external_ref=external_ref),
        )
        return Success(
            output={"customer": CustomerOut.model_validate(created).model_dump(mode="json"), "created": True}
        )


node_executor_registry.register(InstagramFindOrCreateCustomerExecutor())
