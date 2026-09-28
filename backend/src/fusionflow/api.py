"""`/api/v1` router group.

Every module contributes one `APIRouter` here. `/api/admin/*` is mounted
separately in `main.py` (it carries its own audit-logging route class)
rather than under this group. `/api/v1/webhooks/*` is mounted here even
though inbound provider calls are unauthenticated, matching the plan's
route-grouping section, which lists webhooks under `/api/v1/*`.
"""

from fastapi import APIRouter

from fusionflow.modules.auth.router import router as auth_router
from fusionflow.modules.broadcast_campaigns.router import router as broadcast_campaigns_router
from fusionflow.modules.business_objects.router import router as business_objects_router
from fusionflow.modules.business_templates.router import router as business_templates_router
from fusionflow.modules.catalog.router import (
    coupons_router,
    offers_router,
    products_router,
    services_router,
)
from fusionflow.modules.clinic_queue.router import router as clinic_queue_router
from fusionflow.modules.connectors.router import router as connectors_router
from fusionflow.modules.connectors.webhooks import router as connector_webhooks_router
from fusionflow.modules.connectors.instagram.router import router as instagram_settings_router
from fusionflow.modules.connectors.whatsapp.router import router as whatsapp_router
from fusionflow.modules.custom_fields.router import router as custom_fields_router
from fusionflow.modules.customers.router import field_definitions_router as customer_field_definitions_router
from fusionflow.modules.customers.router import router as customers_router
from fusionflow.modules.inbox.router import router as inbox_router
from fusionflow.modules.kb.router import router as kb_router
from fusionflow.modules.media_library.router import router as media_library_router
from fusionflow.modules.orders.router import router as orders_router
from fusionflow.modules.payments.router import router as payments_router
from fusionflow.modules.predefined_automations.router import router as predefined_automations_router
from fusionflow.modules.quick_replies.router import router as quick_replies_router
from fusionflow.modules.tenancy.router import router as tenancy_router
from fusionflow.modules.tickets.router import router as tickets_router
from fusionflow.modules.users.router import router as users_router
from fusionflow.modules.workflows.engine.internal_router import router as workflows_internal_router
from fusionflow.modules.workflows.router import router as workflows_router

API_V1_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_V1_PREFIX)
api_router.include_router(auth_router)
api_router.include_router(business_objects_router)
api_router.include_router(business_templates_router)
api_router.include_router(tenancy_router)
api_router.include_router(custom_fields_router)
api_router.include_router(products_router)
api_router.include_router(services_router)
api_router.include_router(coupons_router)
api_router.include_router(offers_router)
#: Must be included before `customers_router`: `customers_router` has a
#: literal-looking-but-actually-`{customer_id}` route at `/customers/{id}`,
#: and Starlette matches routes in registration order - registering the
#: literal `/customers/field-definitions` path first is what stops it from
#: being swallowed by that `{customer_id}` pattern (which would 422 on the
#: non-UUID segment rather than falling through to this router).
api_router.include_router(customer_field_definitions_router)
api_router.include_router(customers_router)
api_router.include_router(orders_router)
api_router.include_router(payments_router)
api_router.include_router(tickets_router)
api_router.include_router(clinic_queue_router)
api_router.include_router(kb_router)
api_router.include_router(connectors_router)
api_router.include_router(whatsapp_router)
api_router.include_router(instagram_settings_router)
api_router.include_router(connector_webhooks_router)
api_router.include_router(workflows_router)
api_router.include_router(workflows_internal_router)
api_router.include_router(predefined_automations_router)
api_router.include_router(broadcast_campaigns_router)
api_router.include_router(inbox_router)
api_router.include_router(media_library_router)
api_router.include_router(quick_replies_router)
api_router.include_router(users_router)

__all__ = ["API_V1_PREFIX", "api_router"]
