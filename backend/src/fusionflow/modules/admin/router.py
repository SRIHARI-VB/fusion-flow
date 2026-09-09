"""`/api/admin/*` — the super-admin surface.

Every route here requires `require_platform_admin` (from `fusionflow.core.deps`,
already stubbed by Wave 0 - re-checks `users.is_platform_admin` in the DB, not
just the JWT claim) and runs under `AuditLoggingRoute` (see `audit.py`), which
writes one `AuditLog` row per completed request with zero per-endpoint code.

Mounting: this module owns its own full `/api/admin` prefix so mounting it is
a one-line `app.include_router(router)` — see this agent's report for the
exact import path/variable name to wire into `main.py`. Deliberately NOT
mounted here; main.py's router wiring is out of this agent's scope.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status

from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.admin.audit import AuditLoggingRoute
from fusionflow.modules.admin.deps import PlatformAdminDep, SessionDep
from fusionflow.modules.admin.schemas import (
    AuditLogOut,
    AuditLogPage,
    ConnectorHealthOut,
    FeatureFlagCreateRequest,
    FeatureFlagOut,
    FeatureFlagOverrideOut,
    FeatureFlagOverrideUpsertRequest,
    FeatureFlagUpdateRequest,
    FieldTemplateOut,
    FieldTemplatesUnavailableOut,
    ImpersonateRequest,
    ImpersonateResponse,
    TenantDetailOut,
    TenantListItemOut,
)
from fusionflow.modules.admin.service import AdminError

router = APIRouter(prefix="/api/admin", tags=["admin"], route_class=AuditLoggingRoute)


def _http(exc: AdminError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


# --- Tenants -----------------------------------------------------------------


@router.get("/tenants", response_model=list[TenantListItemOut])
async def list_tenants(
    _admin: PlatformAdminDep, session: SessionDep
) -> list[TenantListItemOut]:
    rows = await admin_service.list_tenants(session)
    return [
        TenantListItemOut(
            id=business.id,
            name=business.name,
            slug=business.slug,
            vertical=business.vertical,
            status=business.status,
            member_count=count,
            created_at=business.created_at,
        )
        for business, count in rows
    ]


@router.get("/tenants/{business_id}", response_model=TenantDetailOut)
async def get_tenant_detail(
    business_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> TenantDetailOut:
    business = await admin_service.get_tenant(session, business_id)
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    memberships = await admin_service.get_tenant_memberships(session, business_id)
    return TenantDetailOut(
        id=business.id,
        name=business.name,
        slug=business.slug,
        vertical=business.vertical,
        status=business.status,
        onboarding_completed_at=business.onboarding_completed_at,
        created_at=business.created_at,
        memberships=memberships,
    )


@router.post("/tenants/{business_id}/suspend", response_model=TenantListItemOut)
async def suspend_tenant(
    business_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> TenantListItemOut:
    try:
        business = await admin_service.suspend_tenant(session, business_id)
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    memberships = await admin_service.get_tenant_memberships(session, business_id)
    return TenantListItemOut(
        id=business.id,
        name=business.name,
        slug=business.slug,
        vertical=business.vertical,
        status=business.status,
        member_count=len(memberships),
        created_at=business.created_at,
    )


@router.post("/tenants/{business_id}/reactivate", response_model=TenantListItemOut)
async def reactivate_tenant(
    business_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> TenantListItemOut:
    try:
        business = await admin_service.reactivate_tenant(session, business_id)
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    memberships = await admin_service.get_tenant_memberships(session, business_id)
    return TenantListItemOut(
        id=business.id,
        name=business.name,
        slug=business.slug,
        vertical=business.vertical,
        status=business.status,
        member_count=len(memberships),
        created_at=business.created_at,
    )


@router.get("/tenants/{business_id}/connectors", response_model=ConnectorHealthOut)
async def get_tenant_connectors(
    business_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> ConnectorHealthOut:
    """Cross-tenant connector health. Degrades to `available=False` until
    `modules.connectors.ConnectorInstance` exists - see service.py."""
    business = await admin_service.get_tenant(session, business_id)
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return await admin_service.get_tenant_connector_health(session, business_id)


@router.post("/tenants/{business_id}/impersonate", response_model=ImpersonateResponse)
async def impersonate_tenant_user(
    business_id: uuid.UUID,
    payload: ImpersonateRequest,
    admin: PlatformAdminDep,
    session: SessionDep,
) -> ImpersonateResponse:
    try:
        result = await admin_service.impersonate(
            session,
            admin=admin,
            target_user_id=payload.target_user_id,
            target_business_id=business_id,
            reason=payload.reason,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return ImpersonateResponse(
        access_token=result.access_token,
        expires_in=result.expires_in,
        acting_admin_id=admin.id,
        target_user_id=payload.target_user_id,
        target_business_id=business_id,
        impersonation_session_id=result.session_id,
    )


# --- Audit log ---------------------------------------------------------------


@router.get("/audit-log", response_model=AuditLogPage)
async def get_audit_log(
    _admin: PlatformAdminDep,
    session: SessionDep,
    actor_user_id: uuid.UUID | None = Query(default=None),
    tenant_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None, description="Substring match on the action field"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> AuditLogPage:
    rows, total = await admin_service.list_audit_log(
        session,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        action=action,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return AuditLogPage(items=[AuditLogOut.model_validate(row) for row in rows], total=total)


# --- Feature flags -------------------------------------------------------------


@router.get("/feature-flags", response_model=list[FeatureFlagOut])
async def list_feature_flags(_admin: PlatformAdminDep, session: SessionDep) -> list[FeatureFlagOut]:
    flags = await admin_service.list_feature_flags(session)
    return [FeatureFlagOut.model_validate(f) for f in flags]


@router.post(
    "/feature-flags", response_model=FeatureFlagOut, status_code=status.HTTP_201_CREATED
)
async def create_feature_flag(
    payload: FeatureFlagCreateRequest, _admin: PlatformAdminDep, session: SessionDep
) -> FeatureFlagOut:
    try:
        flag = await admin_service.create_feature_flag(
            session,
            key=payload.key,
            description=payload.description,
            is_global_default=payload.is_global_default,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return FeatureFlagOut.model_validate(flag)


@router.patch("/feature-flags/{flag_id}", response_model=FeatureFlagOut)
async def update_feature_flag(
    flag_id: uuid.UUID,
    payload: FeatureFlagUpdateRequest,
    _admin: PlatformAdminDep,
    session: SessionDep,
) -> FeatureFlagOut:
    try:
        flag = await admin_service.update_feature_flag(
            session,
            flag_id,
            description=payload.description,
            is_global_default=payload.is_global_default,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return FeatureFlagOut.model_validate(flag)


@router.get("/feature-flags/{flag_id}/overrides", response_model=list[FeatureFlagOverrideOut])
async def list_feature_flag_overrides(
    flag_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> list[FeatureFlagOverrideOut]:
    overrides = await admin_service.list_feature_flag_overrides(session, flag_id)
    return [FeatureFlagOverrideOut.model_validate(o) for o in overrides]


@router.post("/feature-flags/{flag_id}/overrides", response_model=FeatureFlagOverrideOut)
async def upsert_feature_flag_override(
    flag_id: uuid.UUID,
    payload: FeatureFlagOverrideUpsertRequest,
    _admin: PlatformAdminDep,
    session: SessionDep,
) -> FeatureFlagOverrideOut:
    try:
        override = await admin_service.upsert_feature_flag_override(
            session, flag_id, tenant_id=payload.tenant_id, enabled=payload.enabled
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return FeatureFlagOverrideOut.model_validate(override)


# --- Global field templates ----------------------------------------------------


@router.get(
    "/templates",
    response_model=list[FieldTemplateOut] | FieldTemplatesUnavailableOut,
)
async def list_templates(_admin: PlatformAdminDep, session: SessionDep):
    return await admin_service.list_field_templates(session)


@router.post("/templates", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def create_template(_admin: PlatformAdminDep) -> dict:
    """Stubbed until `modules.custom_fields.FieldTemplate` lands.

    Kept as a real, discoverable route (rather than omitted) so the frontend
    can call it and render a clear "not available yet" state instead of a
    404 that looks like a typo'd URL - see this agent's report.
    """
    if not admin_service.field_templates_available():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Global field template authoring is not wired up yet: modules.custom_fields.FieldTemplate does not exist in this checkout.",
        )
    raise HTTPException(  # pragma: no cover - unreachable until custom_fields lands
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Template creation exists in the model but is not yet implemented in modules/admin.",
    )


@router.patch("/templates/{template_id}", status_code=status.HTTP_501_NOT_IMPLEMENTED)
async def update_template(template_id: uuid.UUID, _admin: PlatformAdminDep) -> dict:
    """See `create_template` above - same stubbed-until-custom_fields-lands story."""
    if not admin_service.field_templates_available():
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Global field template authoring is not wired up yet: modules.custom_fields.FieldTemplate does not exist in this checkout.",
        )
    raise HTTPException(  # pragma: no cover - unreachable until custom_fields lands
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Template editing exists in the model but is not yet implemented in modules/admin.",
    )


# --- Billing usage (stub) -------------------------------------------------------


@router.get("/billing-usage")
async def get_billing_usage(_admin: PlatformAdminDep, session: SessionDep) -> dict:
    return await admin_service.get_billing_usage_stub(session)
