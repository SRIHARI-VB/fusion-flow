"""Per-module entitlement gate for the 11 fixed feature routers, plus the
per-resource create-time count-limit gate.

`require_module_access(module_key)` is the feature-module analogue of
`fusionflow.core.deps.require_role` - a dependency factory, not a bare
dependency - so each gated router can bind it to its own catalog key
(`require_module_access("products")`, `require_module_access("tickets")`,
...). Lives here rather than in `core/deps.py` to avoid `core` (a
low-level, dependency-free layer) importing upward into a feature module.

Reuses the connector framework's entitlement resolution as-is
(`_tenant_has_connector_access`/`get_connector_access_map` in
`modules.connectors.service`) - that logic already works generically for
any `connector_type_id`, feature-kind or integration-kind, with zero
changes needed here beyond the grandfathering exception below.

`enforce_resource_limit` is a separate, narrower dependency factory for
the same catalog-key vocabulary - it gates a create route's row-count
ceiling (products/services/coupons/.../custom_fields), not whether the
module is reachable at all. Applied per-route (only on the `POST` create
handler), never router-level, since it must not affect GET/PATCH/DELETE.
"""

from __future__ import annotations

from typing import Awaitable, Callable

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.core.deps import SessionDep, TenantContext, TenantContextDep
from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.models import ConnectorCategory
from fusionflow.modules.tenancy.models import Business, BusinessStatus


def require_module_access(module_key: str):
    """Dependency factory: 403s unless the active tenant is entitled to
    `module_key` (bundled in its business template, an approved
    `ConnectorAccessRequest`, or an admin's explicit
    `ConnectorAccessOverride`)."""

    async def _dependency(context: TenantContextDep, session: SessionDep) -> TenantContext:
        connector_type = await connector_service.get_connector_type_by_key(session, module_key)
        if connector_type is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Module '{module_key}' is not registered in the catalog",
            )

        access_map = await connector_service.get_connector_access_map(
            session, tenant_id=context.tenant_id, connector_type_ids=[connector_type.id]
        )
        access_status = access_map.get(connector_type.id, "not_requested")
        if access_status == "granted":
            return context
        if access_status == "denied":
            # An explicit admin revoke (ConnectorAccessOverride) or a denied
            # ConnectorAccessRequest - the grandfathering compat branch below
            # must NEVER rescue an explicit denial, or an admin revoking a
            # module from a pre-template tenant would have no effect at all.
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your business does not have access to this module.",
            )

        # COMPAT: pre-template-system tenants (business_template_id never
        # set) get full access to fixed modules until an admin assigns
        # them a template, or explicitly revokes/grants one - see the plan
        # doc "Next Implementation Phase 2"/"Phase 3". Only rescues
        # "not_requested"/"pending" (handled above, an explicit "denied"
        # already returned). Only applies to FEATURE-category modules,
        # never integration-kind connectors (WhatsApp/Razorpay), which
        # already have real, working entitlement state and don't need
        # grandfathering.
        if connector_type.category == ConnectorCategory.FEATURE:
            business = await session.get(Business, context.tenant_id)
            if (
                business is not None
                and business.business_template_id is None
                and business.status == BusinessStatus.ACTIVE
            ):
                return context

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your business does not have access to this module yet. "
            "Request access from an administrator.",
        )

    return _dependency


def enforce_resource_limit(
    resource_key: str, count_fn: Callable[[AsyncSession, uuid.UUID], Awaitable[int]]
):
    """Dependency factory: 403s if the tenant is already at (or over) its
    resolved row-count limit for `resource_key` (see
    `admin.service.get_resource_limit` for the tenant-override > plan >
    unlimited resolution). `count_fn(session, tenant_id)` counts the
    tenant's current rows for this resource - each caller passes its own
    module's count query (different tables/models per resource), e.g.
    `enforce_resource_limit("products", catalog_service.count_products)`.

    A no-op (unlimited) is the default for any resource with no plan/tenant
    limit configured - this is a hard backend boundary; the frontend
    disabling its own "create" button at the same limit is a UX nicety on
    top, not the actual security boundary.
    """

    async def _dependency(context: TenantContextDep, session: SessionDep) -> None:
        limit = await admin_service.get_resource_limit(
            session, tenant_id=context.tenant_id, resource_key=resource_key
        )
        if limit is None:
            return
        current = await count_fn(session, context.tenant_id)
        if current >= limit:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You've reached your plan's limit of {limit} for this resource.",
            )

    return _dependency
