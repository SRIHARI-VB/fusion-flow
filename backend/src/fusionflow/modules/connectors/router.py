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

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from fusionflow.core.deps import SessionDep, TenantContextDep
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
)
from fusionflow.modules.connectors.service import ConnectorError

# Imported for their registration side effect - see module docstring.
from fusionflow.modules.connectors.razorpay import adapter as _razorpay_adapter  # noqa: F401
from fusionflow.modules.connectors.whatsapp import adapter as _whatsapp_adapter  # noqa: F401

router = APIRouter(prefix="/connectors", tags=["connectors"])
settings = get_connector_settings()


def _http(exc: ConnectorError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/types", response_model=list[ConnectorTypeOut])
async def list_connector_types(context: TenantContextDep, session: SessionDep) -> list[ConnectorTypeOut]:
    """The full provider catalog, plus this tenant's per-type `access_status`
    ("granted"/"pending"/"denied"/"not_requested") so the frontend can render
    Connect vs Request-access vs Pending-approval without a second call."""
    types = await connector_service.list_connector_types(session)
    access_map = await connector_service.get_connector_access_map(
        session, tenant_id=context.tenant_id, connector_type_ids=[t.id for t in types]
    )
    return [connector_service.to_type_out(t, access_map.get(t.id, "not_requested")) for t in types]


@router.get("", response_model=list[ConnectorInstanceOut])
async def list_connectors(context: TenantContextDep, session: SessionDep) -> list[ConnectorInstanceOut]:
    """The tenant's own connector instances (state, health, identity)."""
    instances = await connector_service.list_instances(session, context.tenant_id)
    return [connector_service.to_instance_out(i) for i in instances]


@router.post("/{type_key}/connect", response_model=ConnectResponse)
async def connect_connector(
    type_key: str, payload: ConnectRequest, context: TenantContextDep, session: SessionDep
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
    context: TenantContextDep,
    session: SessionDep,
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
    instance_id: uuid.UUID, context: TenantContextDep, session: SessionDep
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
    instance_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> ConnectorInstanceOut:
    """Frontend must show a confirm dialog before ever calling this."""
    try:
        instance = await connector_service.disconnect(
            session, tenant_id=context.tenant_id, instance_id=instance_id
        )
    except ConnectorError as exc:
        raise _http(exc) from exc
    return connector_service.to_instance_out(instance)


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
