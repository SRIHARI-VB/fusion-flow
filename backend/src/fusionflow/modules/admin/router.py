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
    AdminNodeTypeSummaryOut,
    AssignTenantPlanRequest,
    AuditLogOut,
    AuditLogPage,
    BusinessTemplateCreateRequest,
    BusinessTemplateOut,
    BusinessTemplateUpdateRequest,
    ConnectorAccessOverrideOut,
    ConnectorAccessOverrideRequest,
    ConnectorAccessRequestAdminOut,
    ConnectorAccessRequestReviewOut,
    ConnectorHealthOut,
    ConnectorTypeCatalogOut,
    DenyTenantRequest,
    FeatureFlagCatalogItemOut,
    FeatureFlagCreateRequest,
    FeatureFlagOut,
    FeatureFlagOverrideOut,
    FeatureFlagOverrideUpsertRequest,
    FeatureFlagUpdateRequest,
    FieldTemplateOut,
    FieldTemplatesUnavailableOut,
    GraphValidationIssueOut,
    GraphValidationResultOut,
    ImpersonateRequest,
    ImpersonateResponse,
    PlanCreateRequest,
    PlanFeatureFlagOut,
    PlanFeatureFlagsSetRequest,
    PlanOut,
    PlanResourceLimitOut,
    PlanResourceLimitsSetRequest,
    PlanUpdateRequest,
    ResourceLimitOverrideRequest,
    TenantDetailOut,
    TenantListItemOut,
    TenantModuleAccessOut,
    TenantResourceLimitOut,
    ValidateComponentRequest,
    ValidateStarterTemplateRequest,
    WorkflowComponentCreateRequest,
    WorkflowComponentOut,
    WorkflowComponentUpdateRequest,
    WorkflowNodeTemplateCreateRequest,
    WorkflowNodeTemplateOut,
    WorkflowNodeTemplateUpdateRequest,
    WorkflowStarterTemplateCreateRequest,
    WorkflowStarterTemplateOut,
    WorkflowStarterTemplateUpdateRequest,
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
            denial_reason=business.denial_reason,
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
        denial_reason=business.denial_reason,
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
        denial_reason=business.denial_reason,
    )


@router.post("/tenants/{business_id}/approve", response_model=TenantListItemOut)
async def approve_tenant(
    business_id: uuid.UUID, admin: PlatformAdminDep, session: SessionDep
) -> TenantListItemOut:
    try:
        business = await admin_service.approve_tenant(session, business_id, admin_id=admin.id)
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
        denial_reason=business.denial_reason,
    )


@router.post("/tenants/{business_id}/deny", response_model=TenantListItemOut)
async def deny_tenant(
    business_id: uuid.UUID,
    payload: DenyTenantRequest,
    admin: PlatformAdminDep,
    session: SessionDep,
) -> TenantListItemOut:
    try:
        business = await admin_service.deny_tenant(
            session, business_id, admin_id=admin.id, reason=payload.reason
        )
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
        denial_reason=business.denial_reason,
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


@router.get("/feature-flags/catalog", response_model=list[FeatureFlagCatalogItemOut])
async def list_feature_flag_catalog(_admin: PlatformAdminDep) -> list[FeatureFlagCatalogItemOut]:
    """The "known" flag keys - what the New Flag dropdown offers instead
    of a free-text key field. No DB access: this is static metadata."""
    return [FeatureFlagCatalogItemOut.model_validate(entry) for entry in admin_service.KNOWN_FEATURE_FLAGS]


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


@router.get("/plans/{plan_id}/resource-limits", response_model=list[PlanResourceLimitOut])
async def list_plan_resource_limits(
    plan_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> list[PlanResourceLimitOut]:
    rows = await admin_service.list_plan_resource_limits(session, plan_id)
    return [PlanResourceLimitOut(**row) for row in rows]


@router.put("/plans/{plan_id}/resource-limits", response_model=list[PlanResourceLimitOut])
async def set_plan_resource_limits(
    plan_id: uuid.UUID,
    payload: PlanResourceLimitsSetRequest,
    _admin: PlatformAdminDep,
    session: SessionDep,
) -> list[PlanResourceLimitOut]:
    try:
        await admin_service.set_plan_resource_limits(
            session, plan_id, limits=[(l.resource_key, l.max_count) for l in payload.limits]
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    rows = await admin_service.list_plan_resource_limits(session, plan_id)
    return [PlanResourceLimitOut(**row) for row in rows]


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


# --- Per-tenant module/connector access overrides (revoke/grant) -------------


@router.get("/tenants/{business_id}/module-access", response_model=list[TenantModuleAccessOut])
async def get_tenant_module_access(
    business_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> list[TenantModuleAccessOut]:
    rows = await admin_service.get_tenant_module_access(session, business_id)
    return [TenantModuleAccessOut(**row) for row in rows]


@router.put(
    "/tenants/{business_id}/connectors/{type_key}/override", response_model=ConnectorAccessOverrideOut
)
async def set_connector_access_override(
    business_id: uuid.UUID,
    type_key: str,
    payload: ConnectorAccessOverrideRequest,
    admin: PlatformAdminDep,
    session: SessionDep,
) -> ConnectorAccessOverrideOut:
    try:
        override = await admin_service.set_connector_access_override(
            session,
            business_id,
            type_key,
            granted=payload.granted,
            admin_id=admin.id,
            reason=payload.reason,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    # `updated_at` is DB-computed (`onupdate=func.now()`) and left expired
    # after an UPDATE flush (this is an upsert, so both the create and
    # toggle-existing paths land here) - see
    # `predefined_automations/router.py`'s identical fix for the full
    # explanation of the MissingGreenlet crash this avoids.
    await session.refresh(override, attribute_names=["updated_at"])
    return ConnectorAccessOverrideOut.model_validate(override)


@router.delete("/tenants/{business_id}/connectors/{type_key}/override", status_code=status.HTTP_204_NO_CONTENT)
async def clear_connector_access_override(
    business_id: uuid.UUID, type_key: str, _admin: PlatformAdminDep, session: SessionDep
) -> None:
    try:
        await admin_service.clear_connector_access_override(session, business_id, type_key)
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()


# --- Per-tenant resource count limits -----------------------------------------


@router.get("/tenants/{business_id}/resource-limits", response_model=list[TenantResourceLimitOut])
async def get_tenant_resource_limits(
    business_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> list[TenantResourceLimitOut]:
    rows = await admin_service.get_tenant_resource_limits(session, business_id)
    return [TenantResourceLimitOut(**row) for row in rows]


@router.put("/tenants/{business_id}/resource-limits/{resource_key}", response_model=TenantResourceLimitOut)
async def set_tenant_resource_limit(
    business_id: uuid.UUID,
    resource_key: str,
    payload: ResourceLimitOverrideRequest,
    _admin: PlatformAdminDep,
    session: SessionDep,
) -> TenantResourceLimitOut:
    try:
        await admin_service.set_resource_limit_override(
            session, business_id, resource_key, max_count=payload.max_count
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    rows = await admin_service.get_tenant_resource_limits(session, business_id)
    match = next((r for r in rows if r["resource_key"] == resource_key), None)
    if match is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown resource key")
    return TenantResourceLimitOut(**match)


@router.delete(
    "/tenants/{business_id}/resource-limits/{resource_key}", status_code=status.HTTP_204_NO_CONTENT
)
async def clear_tenant_resource_limit(
    business_id: uuid.UUID, resource_key: str, _admin: PlatformAdminDep, session: SessionDep
) -> None:
    try:
        await admin_service.clear_resource_limit_override(session, business_id, resource_key)
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()


# --- Billing usage (stub) -------------------------------------------------------


@router.get("/billing-usage")
async def get_billing_usage(_admin: PlatformAdminDep, session: SessionDep) -> dict:
    return await admin_service.get_billing_usage_stub(session)


# --- Workflow node templates (admin-managed palette entries, Part D) --------


@router.get("/node-types", response_model=list[AdminNodeTypeSummaryOut])
async def list_admin_node_types(_admin: PlatformAdminDep) -> list[AdminNodeTypeSummaryOut]:
    """Every registered node/trigger type (the raw engine registry, not
    tenant-filtered, not template rows) - lets the admin panel's
    `base_node_type` picker (when authoring a `WorkflowNodeTemplate`) stay
    accurate automatically instead of duplicating a hand-maintained list
    that drifts out of sync with what the engine actually registers (e.g.
    `module.list`/`module.get`/`module.create`/`module.update`, which the
    seed scripts already use as `base_node_type` values today)."""
    # Local import: `workflows.service` already imports FROM this module
    # (`admin_service`) inside `list_node_types_with_templates` - importing
    # it back at module level here would be a circular import.
    from fusionflow.modules.workflows import service as workflows_service

    metas = sorted(workflows_service.list_node_types(), key=lambda m: (m.category, m.label))
    return [
        AdminNodeTypeSummaryOut(node_type=m.node_type, kind=m.kind, label=m.label, category=m.category)
        for m in metas
    ]


@router.get("/workflow-node-templates", response_model=list[WorkflowNodeTemplateOut])
async def list_workflow_node_templates(
    _admin: PlatformAdminDep, session: SessionDep
) -> list[WorkflowNodeTemplateOut]:
    templates = await admin_service.list_workflow_node_templates(session)
    return [WorkflowNodeTemplateOut.model_validate(t) for t in templates]


@router.post(
    "/workflow-node-templates",
    response_model=WorkflowNodeTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_node_template(
    payload: WorkflowNodeTemplateCreateRequest, _admin: PlatformAdminDep, session: SessionDep
) -> WorkflowNodeTemplateOut:
    try:
        template = await admin_service.create_workflow_node_template(
            session,
            key=payload.key,
            label=payload.label,
            description=payload.description,
            category=payload.category,
            base_node_type=payload.base_node_type,
            icon=payload.icon,
            default_config=payload.default_config,
            config_schema_overrides=payload.config_schema_overrides,
            is_active=payload.is_active,
            required_connector_type_key=payload.required_connector_type_key,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return WorkflowNodeTemplateOut.model_validate(template)


@router.patch("/workflow-node-templates/{template_id}", response_model=WorkflowNodeTemplateOut)
async def update_workflow_node_template(
    template_id: uuid.UUID,
    payload: WorkflowNodeTemplateUpdateRequest,
    _admin: PlatformAdminDep,
    session: SessionDep,
) -> WorkflowNodeTemplateOut:
    try:
        template = await admin_service.update_workflow_node_template(
            session,
            template_id,
            label=payload.label,
            description=payload.description,
            category=payload.category,
            icon=payload.icon,
            default_config=payload.default_config,
            config_schema_overrides=payload.config_schema_overrides,
            is_active=payload.is_active,
            required_connector_type_key=payload.required_connector_type_key,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return WorkflowNodeTemplateOut.model_validate(template)


@router.delete("/workflow-node-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_node_template(
    template_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> None:
    try:
        await admin_service.delete_workflow_node_template(session, template_id)
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()


# --- Workflow starter templates (composable-builder redesign, Phase 6) ------


@router.get("/workflow-starter-templates", response_model=list[WorkflowStarterTemplateOut])
async def list_workflow_starter_templates(
    _admin: PlatformAdminDep, session: SessionDep
) -> list[WorkflowStarterTemplateOut]:
    templates = await admin_service.list_workflow_starter_templates(session)
    return [WorkflowStarterTemplateOut.model_validate(t) for t in templates]


@router.post(
    "/workflow-starter-templates",
    response_model=WorkflowStarterTemplateOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_workflow_starter_template(
    payload: WorkflowStarterTemplateCreateRequest, _admin: PlatformAdminDep, session: SessionDep
) -> WorkflowStarterTemplateOut:
    try:
        template = await admin_service.create_workflow_starter_template(
            session,
            key=payload.key,
            name=payload.name,
            description=payload.description,
            category=payload.category,
            icon=payload.icon,
            graph_json=payload.graph_json,
            required_object_types=payload.required_object_types,
            setup_notes=payload.setup_notes,
            is_active=payload.is_active,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return WorkflowStarterTemplateOut.model_validate(template)


# Declared BEFORE `/{template_id}` below - a literal "/validate" segment
# would otherwise be silently swallowed as a `template_id` path parameter
# (FastAPI matches routes in declaration order - the same route-ordering
# bug already hit once this session for `/starter-templates`/`/components`
# on the tenant-facing `workflows/router.py`).
@router.post("/workflow-starter-templates/validate", response_model=GraphValidationResultOut)
async def validate_workflow_starter_template(
    payload: ValidateStarterTemplateRequest, _admin: PlatformAdminDep, session: SessionDep
) -> GraphValidationResultOut:
    """Compiles+validates `graph_json` exactly like publishing a real
    workflow would (see `admin_service.validate_starter_template_graph`) -
    every placeholder connector reference is expected to fail rule 2
    (`disconnected_connector_reference`); that is the accepted passing bar
    for a template, not a real failure."""
    issues, required_keys = await admin_service.validate_starter_template_graph(session, payload.graph_json)
    return GraphValidationResultOut(
        issues=[GraphValidationIssueOut(**i.to_dict()) for i in issues],
        required_connector_type_keys=required_keys,
    )


@router.patch("/workflow-starter-templates/{template_id}", response_model=WorkflowStarterTemplateOut)
async def update_workflow_starter_template(
    template_id: uuid.UUID,
    payload: WorkflowStarterTemplateUpdateRequest,
    _admin: PlatformAdminDep,
    session: SessionDep,
) -> WorkflowStarterTemplateOut:
    try:
        template = await admin_service.update_workflow_starter_template(
            session,
            template_id,
            name=payload.name,
            description=payload.description,
            category=payload.category,
            icon=payload.icon,
            graph_json=payload.graph_json,
            required_object_types=payload.required_object_types,
            setup_notes=payload.setup_notes,
            is_active=payload.is_active,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return WorkflowStarterTemplateOut.model_validate(template)


@router.delete("/workflow-starter-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_starter_template(
    template_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> None:
    try:
        await admin_service.delete_workflow_starter_template(session, template_id)
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()


# --- Workflow components (insertable fragments, composable-builder redesign) -


@router.get("/workflow-components", response_model=list[WorkflowComponentOut])
async def list_workflow_components(_admin: PlatformAdminDep, session: SessionDep) -> list[WorkflowComponentOut]:
    components = await admin_service.list_workflow_components(session)
    return [WorkflowComponentOut.model_validate(c) for c in components]


@router.post("/workflow-components", response_model=WorkflowComponentOut, status_code=status.HTTP_201_CREATED)
async def create_workflow_component(
    payload: WorkflowComponentCreateRequest, _admin: PlatformAdminDep, session: SessionDep
) -> WorkflowComponentOut:
    try:
        component = await admin_service.create_workflow_component(
            session,
            key=payload.key,
            name=payload.name,
            description=payload.description,
            category=payload.category,
            icon=payload.icon,
            graph_fragment=payload.graph_fragment,
            required_object_types=payload.required_object_types,
            setup_notes=payload.setup_notes,
            is_active=payload.is_active,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return WorkflowComponentOut.model_validate(component)


# Declared BEFORE `/{component_id}` below - same route-ordering precaution
# as `/workflow-starter-templates/validate` above.
@router.post("/workflow-components/validate", response_model=GraphValidationResultOut)
async def validate_workflow_component(
    payload: ValidateComponentRequest, _admin: PlatformAdminDep, session: SessionDep
) -> GraphValidationResultOut:
    """Lighter check than the starter-template validator (see
    `admin_service.validate_component_graph`'s docstring) - a component is
    a deliberately partial fragment, so this only checks each node resolves
    to a real registered type with a valid config, not whole-graph rules
    like reachability that assume a complete, publishable workflow."""
    issues, required_keys = await admin_service.validate_component_graph(session, payload.graph_fragment)
    return GraphValidationResultOut(
        issues=[GraphValidationIssueOut(**i.to_dict()) for i in issues],
        required_connector_type_keys=required_keys,
    )


@router.patch("/workflow-components/{component_id}", response_model=WorkflowComponentOut)
async def update_workflow_component(
    component_id: uuid.UUID,
    payload: WorkflowComponentUpdateRequest,
    _admin: PlatformAdminDep,
    session: SessionDep,
) -> WorkflowComponentOut:
    try:
        component = await admin_service.update_workflow_component(
            session,
            component_id,
            name=payload.name,
            description=payload.description,
            category=payload.category,
            icon=payload.icon,
            graph_fragment=payload.graph_fragment,
            required_object_types=payload.required_object_types,
            setup_notes=payload.setup_notes,
            is_active=payload.is_active,
        )
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
    return WorkflowComponentOut.model_validate(component)


@router.delete("/workflow-components/{component_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow_component(
    component_id: uuid.UUID, _admin: PlatformAdminDep, session: SessionDep
) -> None:
    try:
        await admin_service.delete_workflow_component(session, component_id)
    except AdminError as exc:
        raise _http(exc) from exc
    await session.commit()
