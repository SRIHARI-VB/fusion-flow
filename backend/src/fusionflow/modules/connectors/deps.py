"""Per-module entitlement gate for the 11 fixed feature routers.

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
"""

from __future__ import annotations

from fastapi import Depends, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContext, TenantContextDep
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.models import ConnectorCategory
from fusionflow.modules.tenancy.models import Business, BusinessStatus


def require_module_access(module_key: str):
    """Dependency factory: 403s unless the active tenant is entitled to
    `module_key` (bundled in its business template, or an approved
    `ConnectorAccessRequest`)."""

    async def _dependency(context: TenantContextDep, session: SessionDep) -> TenantContext:
        connector_type = await connector_service.get_connector_type_by_key(session, module_key)
        if connector_type is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Module '{module_key}' is not registered in the catalog",
            )

        # COMPAT: pre-template-system tenants (business_template_id never
        # set) get full access to fixed modules until an admin assigns
        # them a template - see the plan doc "Next Implementation Phase 2".
        # Only applies to FEATURE-category modules, never to integration
        # -kind connectors (WhatsApp/Razorpay), which already have real,
        # working entitlement state today and don't need grandfathering.
        if connector_type.category == ConnectorCategory.FEATURE:
            business = await session.get(Business, context.tenant_id)
            if (
                business is not None
                and business.business_template_id is None
                and business.status == BusinessStatus.ACTIVE
            ):
                return context

        granted = await connector_service._tenant_has_connector_access(
            session, tenant_id=context.tenant_id, connector_type_id=connector_type.id
        )
        if not granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your business does not have access to this module yet. "
                "Request access from an administrator.",
            )
        return context

    return _dependency
