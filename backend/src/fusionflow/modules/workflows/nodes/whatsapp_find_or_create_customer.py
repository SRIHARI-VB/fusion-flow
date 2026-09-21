"""`whatsapp.find_or_create_customer` — the bridge between a WhatsApp
automation and the Customers module: looks up a `Customer` by phone
(typically `{{trigger.from}}`), creating one if none exists.

Not a WhatsApp API call at all - a plain Customers-module operation keyed
off a WhatsApp payload field - so unlike its sibling files in this module
it imports no WhatsApp adapter, only `modules/customers/service.py`.
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
    phone: str = Field(
        min_length=1,
        description="Phone number, typically '{{trigger.from}}'.",
        json_schema_extra={"format": "recipient"},
    )
    name: str | None = Field(
        default=None, description="Fallback name to use if a new customer must be created."
    )


class FindOrCreateCustomerExecutor(NodeExecutor):
    node_type = "whatsapp.find_or_create_customer"
    kind = "action"
    category = "Messages"
    subcategory = "Contact"
    label = "Find or Create Customer by Phone"
    description = "Looks up a Customer by phone number (e.g. the WhatsApp sender), creating one if none exists."
    config_model = FindOrCreateCustomerConfig
    required_connector_type_key = "customers"
    # Account/CRM utility, not conversation content - keep it out of "Talk to
    # Customer" (the daily-use group for a WhatsApp-flow builder) so that
    # group stays focused on messages a customer actually sees.
    palette_group = "Advanced"
    # Per-recipient identity resolution is legitimate inside a broadcast's
    # loop too (e.g. resolve/create a Customer record per recipient before
    # personalizing a send) - explicit "both", not just left unset, for
    # clarity next to its automation-only siblings in this same file family.
    applicable_purposes = ["automation", "broadcast"]
    output_schema = _OUTPUT_SCHEMA
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = FindOrCreateCustomerConfig.model_validate(context.config)
        phone = interpolate(config.phone, context.variables)
        name = interpolate(config.name, context.variables) if config.name else None

        existing = await customers_service.get_customer_by_phone(context.session, context.tenant_id, phone)
        if existing is not None:
            return Success(output={"customer": CustomerOut.model_validate(existing).model_dump(mode="json"), "created": False})

        created = await customers_service.create_customer(
            context.session,
            context.tenant_id,
            CustomerCreate(name=name or phone, phone=phone),
        )
        return Success(
            output={"customer": CustomerOut.model_validate(created).model_dump(mode="json"), "created": True}
        )


node_executor_registry.register(FindOrCreateCustomerExecutor())
