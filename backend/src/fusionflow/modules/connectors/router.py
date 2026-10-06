"""`/connectors` — generic connector lifecycle routes.

Mount point (see this task's final report for the exact snippet): this
`router` is intended to be included into `fusionflow.api.api_router`
alongside `auth_router`/`tenancy_router`, giving final paths under
`/api/v1/connectors/...`. Not wired up here - `api.py` router mounting is
outside this module's ownership boundary for this wave.

Every handler below calls straight into `service.py`; none of them
branch on `type_key`/provider. The two provider adapter modules are
imported below purely for their import-time
`base.registry.register(...)` side effect (same pattern as
`fusionflow.db.models`'s "imported for its side effect" import in
`main.py`) - remove either import and that provider simply stops being
connectable, with no other code change required.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse

from fusionflow.core.deps import SessionDep, TenantContext, TenantContextDep, require_role
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.config import get_connector_settings
from fusionflow.modules.connectors.schemas import (
    ConnectorAccessRequestCreate,
    ConnectorAccessRequestOut,
    ConnectorEventOut,
    ConnectorInstanceOut,
    ConnectorTypeOut,
    ConnectRequest,
    ConnectResponse,
    MediaUploadOut,
    ModuleRoleAccessOut,
    SetRoleRestrictionRequest,
)
from fusionflow.modules.connectors.models import ConnectorCategory, ConnectorType
from fusionflow.modules.connectors.module_dependencies import MODULE_DEPENDENCIES, dependents_of
from fusionflow.modules.connectors.service import NON_MODULE_KEYS, ConnectorError
from fusionflow.modules.media_library import service as media_library_service
from fusionflow.modules.tenancy.models import MembershipRole

# Imported for their registration side effect - see module docstring.
from fusionflow.modules.connectors.cloudflare_r2 import adapter as _cloudflare_r2_adapter  # noqa: F401
from fusionflow.modules.connectors.facebook import adapter as _facebook_adapter  # noqa: F401
from fusionflow.modules.connectors.gmail import adapter as _gmail_adapter  # noqa: F401
from fusionflow.modules.connectors.google_calendar import adapter as _google_calendar_adapter  # noqa: F401
from fusionflow.modules.connectors.google_meet import adapter as _google_meet_adapter  # noqa: F401
from fusionflow.modules.connectors.google_sheets import adapter as _google_sheets_adapter  # noqa: F401
from fusionflow.modules.connectors.instagram import adapter as _instagram_adapter  # noqa: F401
from fusionflow.modules.connectors.razorpay import adapter as _razorpay_adapter  # noqa: F401
from fusionflow.modules.connectors.telegram import adapter as _telegram_adapter  # noqa: F401
from fusionflow.modules.connectors.whatsapp import adapter as _whatsapp_adapter  # noqa: F401

router = APIRouter(prefix="/connectors", tags=["connectors"])
settings = get_connector_settings()

# No pre-existing upload-size convention anywhere in this codebase (this is
# the first file-upload endpoint) - an explicit 16MB cap rather than an
# unbounded read of the request body.
_MAX_UPLOAD_BYTES = 16 * 1024 * 1024


def _http(exc: ConnectorError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/types", response_model=list[ConnectorTypeOut])
async def list_connector_types(context: TenantContextDep, session: SessionDep) -> list[ConnectorTypeOut]:
    """The full provider catalog, plus this tenant's per-type `access_status`
    ("granted"/"pending"/"denied"/"restricted"/"not_requested") so the
    frontend can render Connect vs Request-access vs Pending-approval vs
    role-restricted without a second call. Resolved for the CALLER's own
    role, not just the tenant - see `get_connector_access_map_for_role`."""
    types = await connector_service.list_connector_types(session)
    access_map = await connector_service.resolve_module_access_map(
        session, tenant_id=context.tenant_id, connector_types=types, role=context.role
    )
    return [connector_service.to_type_out(t, access_map.get(t.id, "not_requested")) for t in types]


@router.get("/role-restrictions", response_model=list[ModuleRoleAccessOut])
async def list_role_restrictions(
    session: SessionDep,
    context: TenantContext = Depends(require_role(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> list[ModuleRoleAccessOut]:
    """FEATURE modules this tenant has, each with whether Member/Viewer are
    currently restricted from it. Owner/Admin only - powers the Settings
    "Team Permissions" tab."""
    rows = await connector_service.list_module_role_access(session, tenant_id=context.tenant_id)
    return [
        ModuleRoleAccessOut(
            connector_type_id=t.id,
            key=t.key,
            display_name=t.display_name,
            member_restricted=member_restricted,
            viewer_restricted=viewer_restricted,
            depends_on=list(MODULE_DEPENDENCIES.get(t.key, [])),
            dependents=dependents_of(t.key),
        )
        for t, member_restricted, viewer_restricted in rows
    ]


@router.put("/role-restrictions", status_code=204)
async def set_role_restriction(
    payload: SetRoleRestrictionRequest,
    session: SessionDep,
    context: TenantContext = Depends(require_role(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> None:
    """Restrict (or un-restrict) one module for one role, tenant-scoped.
    Owner/Admin only, and only Member/Viewer can ever be the target role -
    Owner/Admin are never restrictable (see `RoleModuleRestriction`'s
    docstring)."""
    if payload.role not in (MembershipRole.MEMBER, MembershipRole.VIEWER):
        raise HTTPException(
            status_code=400, detail="Only the member or viewer role can be restricted"
        )
    connector_type = await session.get(ConnectorType, payload.connector_type_id)
    if connector_type is None:
        raise HTTPException(status_code=404, detail="Module not found")
    if connector_type.category != ConnectorCategory.FEATURE or connector_type.key in NON_MODULE_KEYS:
        raise HTTPException(status_code=400, detail="Only feature modules can be restricted by role")
    tenant_access = await connector_service.resolve_module_access(
        session, tenant_id=context.tenant_id, connector_type=connector_type, role=None
    )
    if tenant_access != "granted":
        raise HTTPException(status_code=409, detail="Your business does not have this module")
    await connector_service.set_role_module_restriction(
        session,
        tenant_id=context.tenant_id,
        connector_type_id=payload.connector_type_id,
        role=payload.role,
        restricted=payload.restricted,
    )
    await commit_and_keep_tenant_context(session)


@router.get("", response_model=list[ConnectorInstanceOut])
async def list_connectors(context: TenantContextDep, session: SessionDep) -> list[ConnectorInstanceOut]:
    """The tenant's own connector instances (state, health, identity)."""
    instances = await connector_service.list_instances(session, context.tenant_id)
    return [connector_service.to_instance_out(i) for i in instances]


@router.post("/{type_key}/connect", response_model=ConnectResponse)
async def connect_connector(
    type_key: str,
    payload: ConnectRequest,
    session: SessionDep,
    context: TenantContext = Depends(require_role(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> ConnectResponse:
    """Start (api_key providers: complete) a connection for `type_key`."""
    try:
        instance, result = await connector_service.connect(
            session,
            tenant_id=context.tenant_id,
            type_key=type_key,
            display_name=payload.display_name,
            params=payload.params,
        )
    except ConnectorError as exc:
        raise _http(exc) from exc
    except Exception as exc:  # noqa: BLE001 - see service.connect's docstring: adapter-raised
        # exceptions (bad credentials, provider rejection, ...) propagate as-is from the
        # adapter on purpose, precisely so this route can surface them as a clean 400
        # instead of the framework-error shape ConnectorError represents. Without this,
        # e.g. an invalid Razorpay key pair 500s instead of returning a useful message.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ConnectResponse(instance=connector_service.to_instance_out(instance), redirect_url=result.redirect_url)


@router.post("/{type_key}/request-access", response_model=ConnectorAccessRequestOut, status_code=201)
async def request_connector_access(
    type_key: str,
    payload: ConnectorAccessRequestCreate,
    session: SessionDep,
    context: TenantContext = Depends(require_role(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> ConnectorAccessRequestOut:
    """A tenant asking an admin to grant a connector outside its
    business-template bundle. Feeds the admin's cross-tenant
    `/api/admin/connector-access-requests` queue."""
    try:
        request = await connector_service.request_access(
            session,
            tenant_id=context.tenant_id,
            type_key=type_key,
            requested_by=context.user.id,
            reason=payload.reason,
        )
    except ConnectorError as exc:
        raise _http(exc) from exc
    return connector_service.to_access_request_out(request)


@router.get("/oauth/callback/{type_key}")
async def oauth_callback(
    type_key: str,
    session: SessionDep,
    state: str = Query(...),
    code: str | None = Query(default=None),
    error: str | None = Query(default=None),
    error_description: str | None = Query(default=None),
) -> RedirectResponse:
    """Generic OAuth callback: resolve `state` -> tenant/instance, delegate.

    Unauthenticated by design (the provider, not our frontend, calls
    this) - `state` is the sole correlation token, see
    `service._consume_oauth_state`. Always redirects the browser back
    into `frontend/web` rather than returning JSON, since the caller here
    is the user's browser mid-redirect-chain, not an API client.
    """
    frontend_base = settings.FRONTEND_BASE_URL.rstrip("/")

    if error or code is None:
        detail = error_description or error or "Missing authorization code"
        return RedirectResponse(
            url=f"{frontend_base}/connectors/{type_key}/connect?error={detail}",
            status_code=302,
        )

    try:
        instance, _result = await connector_service.complete_oauth_callback(
            session, type_key=type_key, state_token=state, code=code
        )
    except ConnectorError as exc:
        return RedirectResponse(
            url=f"{frontend_base}/connectors/{type_key}/connect?error={exc.detail}",
            status_code=302,
        )
    except Exception as exc:  # noqa: BLE001 - same rationale as connect_connector above:
        # the browser is mid-redirect here, so even a provider-side adapter failure must
        # end in a redirect, never a raw 500 page.
        return RedirectResponse(
            url=f"{frontend_base}/connectors/{type_key}/connect?error={exc}",
            status_code=302,
        )

    return RedirectResponse(url=f"{frontend_base}/connectors/{instance.id}?connected=1", status_code=302)


@router.post("/{instance_id}/test", response_model=ConnectorInstanceOut)
async def test_connector(
    instance_id: uuid.UUID,
    session: SessionDep,
    context: TenantContext = Depends(require_role(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> ConnectorInstanceOut:
    try:
        instance = await connector_service.test_connection(
            session, tenant_id=context.tenant_id, instance_id=instance_id
        )
    except ConnectorError as exc:
        raise _http(exc) from exc
    return connector_service.to_instance_out(instance)


@router.post("/{instance_id}/disconnect", response_model=ConnectorInstanceOut)
async def disconnect_connector(
    instance_id: uuid.UUID,
    session: SessionDep,
    context: TenantContext = Depends(require_role(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> ConnectorInstanceOut:
    """Frontend must show a confirm dialog before ever calling this."""
    try:
        instance = await connector_service.disconnect(
            session, tenant_id=context.tenant_id, instance_id=instance_id
        )
    except ConnectorError as exc:
        raise _http(exc) from exc
    return connector_service.to_instance_out(instance)


@router.post("/{instance_id}/media", response_model=MediaUploadOut)
async def upload_media(
    instance_id: uuid.UUID,
    context: TenantContextDep,
    session: SessionDep,
    file: UploadFile = File(...),
) -> MediaUploadOut:
    """Uploads `file` to the tenant's connected Cloudflare R2 bucket and
    returns its (provider-hosted) URL.

    The first general file-upload endpoint in this codebase - unrelated to
    WhatsApp's own `media_id` concept (Meta-hosted media reachable only
    through Meta's Graph API). 404s for a missing instance or one that
    isn't a `cloudflare_r2` connector, same instance-scoped-lookup
    convention as `test_connector`/`disconnect_connector` above.
    """
    instance = await connector_service.get_instance(session, tenant_id=context.tenant_id, instance_id=instance_id)
    if instance is None or instance.connector_type.key != _cloudflare_r2_adapter.adapter.connector_type_key:
        raise HTTPException(status_code=404, detail="Cloudflare R2 connector instance not found")

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413, detail=f"File exceeds the {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB upload limit"
        )

    try:
        url = await _cloudflare_r2_adapter.adapter.upload_object(
            instance=instance,
            session=session,
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as exc:  # noqa: BLE001 - same rationale as connect_connector: surface a clean 400
        # rather than a raw 500 for a provider-side upload failure (bad/rotated credentials, bucket
        # deleted, network unreachable, ...).
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await media_library_service.create_media_asset(
        session,
        tenant_id=context.tenant_id,
        url=url,
        filename=file.filename or "upload",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(file_bytes),
        source="cloudflare_r2",
    )
    await commit_and_keep_tenant_context(session)

    return MediaUploadOut(url=url)


@router.get("/{instance_id}/events", response_model=list[ConnectorEventOut])
async def list_connector_events(
    instance_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> list[ConnectorEventOut]:
    try:
        events = await connector_service.list_events(
            session, tenant_id=context.tenant_id, instance_id=instance_id
        )
    except ConnectorError as exc:
        raise _http(exc) from exc
    return [ConnectorEventOut.model_validate(e) for e in events]
