"""`/api/v1/auth` — signup, login, refresh, logout, select-business, me."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Cookie, HTTPException, Response, status

from fusionflow.core.deps import CurrentUserDep, SessionDep, TokenPayloadDep
from fusionflow.modules.auth import service as auth_service
from fusionflow.modules.auth.http import (
    REFRESH_COOKIE_NAME,
    clear_refresh_cookie,
    set_refresh_cookie,
    to_token_response,
)
from fusionflow.modules.auth.schemas import (
    LoginRequest,
    MeResponse,
    RefreshRequest,
    SelectBusinessRequest,
    SignupRequest,
    SignupResult,
    TokenResponse,
    UserOut,
)
from fusionflow.modules.auth.service import AuthError
from fusionflow.modules.tenancy import service as tenancy_service

router = APIRouter(prefix="/auth", tags=["auth"])

RefreshCookieDep = Annotated[str | None, Cookie(alias=REFRESH_COOKIE_NAME)]
RefreshBodyDep = Annotated[RefreshRequest | None, Body()]


def _http(exc: AuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/signup", response_model=SignupResult, status_code=status.HTTP_201_CREATED)
async def signup(payload: SignupRequest, session: SessionDep) -> SignupResult:
    """Create a user, their first business (pending admin approval), and an
    owner membership. Issues no session - see `SignupResult`."""
    try:
        business = await auth_service.signup(
            session,
            email=payload.email,
            password=payload.password,
            business_name=payload.business_name,
            vertical=payload.vertical,
            business_template_id=payload.business_template_id,
            extra_connector_type_keys=tuple(payload.extra_connector_type_keys),
        )
    except AuthError as exc:
        raise _http(exc) from exc
    return SignupResult(status="pending_approval", business_id=business.id, business_name=business.name)


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, response: Response, session: SessionDep) -> TokenResponse:
    """Log in. Multi-business users get a pre-tenant token (see TokenResponse)."""
    try:
        issued = await auth_service.login(session, email=payload.email, password=payload.password)
    except AuthError as exc:
        raise _http(exc) from exc
    set_refresh_cookie(response, issued.refresh_token_raw)
    return to_token_response(issued)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    response: Response,
    session: SessionDep,
    refresh_cookie: RefreshCookieDep = None,
    payload: RefreshBodyDep = None,
) -> TokenResponse:
    """Rotate the refresh token. Reuse of an already-rotated token kills the family."""
    raw_token = refresh_cookie or (payload.refresh_token if payload else None)
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="No refresh token provided"
        )
    try:
        issued = await auth_service.refresh(session, raw_token=raw_token)
    except AuthError as exc:
        clear_refresh_cookie(response)
        raise _http(exc) from exc
    set_refresh_cookie(response, issued.refresh_token_raw)
    return to_token_response(issued)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session: SessionDep,
    refresh_cookie: RefreshCookieDep = None,
    payload: RefreshBodyDep = None,
) -> Response:
    """Revoke the current refresh token. Idempotent - always 204."""
    raw_token = refresh_cookie or (payload.refresh_token if payload else None)
    await auth_service.logout(session, raw_token=raw_token)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_refresh_cookie(response)
    return response


@router.post("/select-business", response_model=TokenResponse)
async def select_business(
    payload: SelectBusinessRequest,
    response: Response,
    user: CurrentUserDep,
    session: SessionDep,
) -> TokenResponse:
    """Exchange any valid access token for one scoped to `business_id`."""
    try:
        issued = await auth_service.select_business(
            session, user=user, business_id=payload.business_id
        )
    except AuthError as exc:
        raise _http(exc) from exc
    set_refresh_cookie(response, issued.refresh_token_raw)
    return to_token_response(issued)


@router.get("/me", response_model=MeResponse)
async def me(payload: TokenPayloadDep, user: CurrentUserDep, session: SessionDep) -> MeResponse:
    """Identity + current tenant scope. Works with a pre-tenant token too."""
    return MeResponse(
        user=UserOut.model_validate(user),
        tenant_id=payload.get("tenant_id"),
        role=payload.get("role"),
        platform_admin=bool(payload.get("platform_admin")),
        memberships=await tenancy_service.list_business_memberships(session, user.id),
    )
