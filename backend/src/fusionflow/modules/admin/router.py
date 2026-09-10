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
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.admin.audit import AuditLoggingRoute
from fusionflow.modules.admin.deps import PlatformAdminDep, SessionDep
from fusionflow.modules.admin.schemas import (
    AssignTenantPlanRequest,
    AuditLogOut,
    AuditLogPage,
    BusinessTemplateCreateRequest,
    BusinessTemplateOut,
    BusinessTemplateUpdateRequest,
    ConnectorAccessRequestAdminOut,
    ConnectorAccessRequestReviewOut,
    ConnectorHealthOut,
    ConnectorTypeCatalogOut,
    FeatureFlagCreateRequest,
    FeatureFlagOut,
    FeatureFlagOverrideOut,
    FeatureFlagOverrideUpsertRequest,
    FeatureFlagUpdateRequest,
    FieldTemplateOut,
    FieldTemplatesUnavailableOut,
    ImpersonateRequest,
    ImpersonateResponse,
    PlanCreateRequest,
    PlanFeatureFlagOut,
    PlanFeatureFlagsSetRequest,
    PlanOut,
    PlanUpdateRequest,
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


# NOTE on the old `POST /templates` / `PATCH /templates/{id}` 501 stubs that
# used to live here: they were placeholders for authoring
# `modules.custom_fields.FieldTemplate` (the per-entity-type custom-field
# bundle listed read-only by `GET /templates` above), a concept this task
# deliberately does not touch (see this task's report - conflating it with
# the new `BusinessTemplate` "starter kit" concept below was flagged
# explicitly as something to avoid). `GET /templates` above is untouched.
# The two 501 stubs are removed rather than repurposed - full CRUD for the
# new, distinct `BusinessTemplate` model lives at `/admin/business-templates`
# below instead, so nothing that previously worked (the read-only `GET
# /templates` list) changes shape, and nothing that never worked (the two
# stubs) is left half-real under a misleading old path.


# --- Plans ---------------------------------------------------------------


@router.get("/plans", response_model=list[PlanOut])
async def list_plans(_admin: PlatformAdminDep, session: SessionDep) -> list[PlanOut]:
    plans = await admin_service.list_plans(session)
    return [PlanOut.model_validate(p) for p in plans]


@router.post("/plans", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def create_plan(
    payload: PlanCreateRequest, _admin: PlatformAdminDep, session: SessionDep
) -> PlanOut:
    try:
        plan = await admin_service.create_plan(
            session, key=payload.key, name=payload.name, is_default=payload.is_default
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return PlanOut.model_validate(plan)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: uuid.UUID, payload: PlanUpdateRequest, _admin: PlatformAdminDep, session: SessionDep
) -> PlanOut:
    try:
        plan = await admin_service.update_plan(
            session, plan_id, name=payload.name, is_default=payload.is_default
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return PlanOut.model_validate(plan)


@router.get("/plans/{plan_id}/feature-flags", response_model=list[PlanFeatureFlagOut])
async def list_plan_feature_flags(
    plan_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> list[PlanFeatureFlagOut]:
    rows = await admin_service.list_plan_feature_flags(session, plan_id)
    return [PlanFeatureFlagOut.model_validate(r) for r in rows]


@router.put("/plans/{plan_id}/feature-flags", response_model=list[PlanFeatureFlagOut])
async def set_plan_feature_flags(
    plan_id: uuid.UUID,
    payload: PlanFeatureFlagsSetRequest,
    _admin: PlatformAdminDep,
    session: SessionDep,
) -> list[PlanFeatureFlagOut]:
    try:
        rows = await admin_service.set_plan_feature_flags(
            session, plan_id, flags=[(f.feature_flag_id, f.enabled) for f in payload.flags]
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return [PlanFeatureFlagOut.model_validate(r) for r in rows]


@router.post("/tenants/{business_id}/plan", response_model=TenantListItemOut)
async def assign_tenant_plan(
    business_id: uuid.UUID,
    payload: AssignTenantPlanRequest,
    _admin: PlatformAdminDep,
    session: SessionDep,
) -> TenantListItemOut:
    """Assign (or unassign, `plan_id=None`) a tenant's plan directly -
    independent of whether it ever applied a `BusinessTemplate`."""
    try:
        business = await admin_service.assign_tenant_plan(session, business_id, plan_id=payload.plan_id)
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


@router.get("/connector-types", response_model=list[ConnectorTypeCatalogOut])
async def list_connector_type_catalog(
    _admin: PlatformAdminDep, session: SessionDep
) -> list[ConnectorTypeCatalogOut]:
    """Global catalog, for the business-template "pick connectors" UI."""
    rows = await admin_service.list_connector_type_catalog(session)
    return [ConnectorTypeCatalogOut(**row) for row in rows]


# --- Business templates (starter kits) ---------------------------------------


async def _to_business_template_out(session: AsyncSession, template) -> BusinessTemplateOut:
    connector_type_ids = await admin_service.get_business_template_connector_type_ids(session, template.id)
    return BusinessTemplateOut(
        id=template.id,
        key=template.key,
        name=template.name,
        description=template.description,
        vertical=template.vertical,
        plan_id=template.plan_id,
        is_active=template.is_active,
        created_at=template.created_at,
        connector_type_ids=connector_type_ids,
    )


@router.get("/business-templates", response_model=list[BusinessTemplateOut])
async def list_business_templates(
    _admin: PlatformAdminDep, session: SessionDep
) -> list[BusinessTemplateOut]:
    templates = await admin_service.list_business_templates(session)
    return [await _to_business_template_out(session, t) for t in templates]


@router.get("/business-templates/{template_id}", response_model=BusinessTemplateOut)
async def get_business_template(
    template_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> BusinessTemplateOut:
    template = await admin_service.get_business_template(session, template_id)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business template not found")
    return await _to_business_template_out(session, template)


@router.post(
    "/business-templates", response_model=BusinessTemplateOut, status_code=status.HTTP_201_CREATED
)
async def create_business_template(
    payload: BusinessTemplateCreateRequest, _admin: PlatformAdminDep, session: SessionDep
) -> BusinessTemplateOut:
    try:
        template = await admin_service.create_business_template(
            session,
            key=payload.key,
            name=payload.name,
            description=payload.description,
            vertical=payload.vertical,
            plan_id=payload.plan_id,
            is_active=payload.is_active,
            connector_type_ids=payload.connector_type_ids,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return await _to_business_template_out(session, template)


@router.patch("/business-templates/{template_id}", response_model=BusinessTemplateOut)
async def update_business_template(
    template_id: uuid.UUID,
    payload: BusinessTemplateUpdateRequest,
    _admin: PlatformAdminDep,
    session: SessionDep,
) -> BusinessTemplateOut:
    try:
        template = await admin_service.update_business_template(
            session,
            template_id,
            name=payload.name,
            description=payload.description,
            vertical=payload.vertical,
            plan_id=payload.plan_id,
            is_active=payload.is_active,
            connector_type_ids=payload.connector_type_ids,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return await _to_business_template_out(session, template)


# --- Connector access requests (cross-tenant admin queue) --------------------


@router.get("/connector-access-requests", response_model=list[ConnectorAccessRequestAdminOut])
async def list_connector_access_requests(
    _admin: PlatformAdminDep,
    status_filter: str | None = Query(default=None, alias="status"),
) -> list[ConnectorAccessRequestAdminOut]:
    """Pending-first, cross-tenant. Reads over `unscoped_session_factory` -
    see `admin_service.list_connector_access_requests`'s docstring - so this
    handler deliberately takes no `SessionDep` of its own."""
    rows = await admin_service.list_connector_access_requests(status_filter=status_filter)
    return [ConnectorAccessRequestAdminOut(**row) for row in rows]


@router.post(
    "/connector-access-requests/{request_id}/approve", response_model=ConnectorAccessRequestReviewOut
)
async def approve_connector_access_request(
    request_id: uuid.UUID, admin: PlatformAdminDep, session: SessionDep
) -> ConnectorAccessRequestReviewOut:
    try:
        request = await admin_service.approve_connector_access_request(
            session, request_id, admin_id=admin.id
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return ConnectorAccessRequestReviewOut(
        id=request.id,
        tenant_id=request.tenant_id,
        status=request.status.value,
        reviewed_by=request.reviewed_by,
        reviewed_at=request.reviewed_at,
    )


@router.post(
    "/connector-access-requests/{request_id}/deny", response_model=ConnectorAccessRequestReviewOut
)
async def deny_connector_access_request(
    request_id: uuid.UUID, admin: PlatformAdminDep, session: SessionDep
) -> ConnectorAccessRequestReviewOut:
    try:
        request = await admin_service.deny_connector_access_request(
            session, request_id, admin_id=admin.id
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return ConnectorAccessRequestReviewOut(
        id=request.id,
        tenant_id=request.tenant_id,
        status=request.status.value,
        reviewed_by=request.reviewed_by,
        reviewed_at=request.reviewed_at,
    )


# --- Billing usage (stub) -------------------------------------------------------


@router.get("/billing-usage")
async def get_billing_usage(_admin: PlatformAdminDep, session: SessionDep) -> dict:
    return await admin_service.get_billing_usage_stub(session)
