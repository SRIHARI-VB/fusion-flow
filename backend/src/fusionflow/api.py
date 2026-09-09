"""`/api/v1` router group.

Every module contributes one `APIRouter` here. Later waves add
custom-fields, products/services/coupons/offers, the fixed connectors, the
connector framework, workflows and webhooks in the same way; `/api/admin/*`
is mounted separately (it has its own audit middleware) rather than under
this group.
"""

from fastapi import APIRouter

from fusionflow.modules.auth.router import router as auth_router
from fusionflow.modules.tenancy.router import router as tenancy_router

API_V1_PREFIX = "/api/v1"

api_router = APIRouter(prefix=API_V1_PREFIX)
api_router.include_router(auth_router)
api_router.include_router(tenancy_router)

__all__ = ["API_V1_PREFIX", "api_router"]
