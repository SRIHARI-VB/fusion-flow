"""Shared Google OAuth2 (authorization-code, offline access) helper.

Used by all four Google connector adapters (`google_calendar`, `gmail`,
`google_meet`, `google_sheets`) - they differ only in the `scopes` they
request and the product-specific API calls they make once a token is
in hand. This is the first real exercise of the OAuth scaffolding in
`connectors/base.py`/`service.py` (`ConnectorOAuthState`,
`create_oauth_state`, `complete_oauth_callback`) - WhatsApp/Razorpay/
Cloudflare R2 are all `auth_mode="api_key"` and never touch it.

Stub-on-network-unreachable convention (matches `whatsapp/adapter.py`,
`razorpay/adapter.py`, `cloudflare_r2/adapter.py` exactly): a real rejection
from Google (bad code, bad refresh token, revoked grant) raises `ValueError`
and must surface as a clean error. Initial development connections can use
stubs when offline; refreshing a real credential always propagates network
errors so a temporary outage never overwrites it with a fabricated token.

Credential shape stored by every Google adapter via
`connector_service.upsert_credential` (a small JSON dict, Fernet-encrypted -
see `connectors/models.py::ConnectorCredential`):
    {"access_token": str, "refresh_token": str, "expires_at": float (unix
     seconds), "scope": str, "token_type": str}
`refresh_token` is only ever returned by Google on the FIRST authorization
(with `access_type=offline&prompt=consent`) - `_merge_refresh_response`
below is what keeps it from being dropped on every subsequent refresh
(Google's refresh response omits it).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import ConnectorReconnectRequired
from fusionflow.modules.connectors.config import get_connector_settings
from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState, HealthStatus

logger = logging.getLogger(__name__)
settings = get_connector_settings()

# Mirrors whatsapp/adapter.py::_NETWORK_UNREACHABLE_ERRORS exactly - only
# "could not reach Google at all" falls back to a stub; a real 4xx
# rejection from Google is a genuine error and must propagate.
_NETWORK_UNREACHABLE_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.TimeoutException)

# expires_in is reported in seconds by Google; refresh this many seconds
# early so a token that's about to expire mid-call still gets renewed.
_EXPIRY_SKEW_SECONDS = 60

_RECONNECT_MESSAGE = (
    "Google authorization has expired or been revoked. Reconnect this Google connector in Integrations."
)


class GoogleReconnectRequired(ConnectorReconnectRequired):
    def __init__(self) -> None:
        super().__init__(_RECONNECT_MESSAGE)


@dataclass
class GoogleTokenResult:
    is_stub: bool
    detail: str | None
    access_token: str
    refresh_token: str | None
    expires_at: float
    scope: str | None
    token_type: str


def oauth_redirect_uri(type_key: str) -> str:
    """The `redirect_uri` registered in Google Cloud Console for `type_key`.

    Each Google connector gets its own callback path (the generic `GET
    /connectors/oauth/callback/{type_key}` route in router.py) despite all
    four sharing one OAuth app/client id - Google requires every
    `redirect_uri` a client will ever use to be pre-registered, so all four
    paths must be added to the same OAuth app's allow-list.
    """
    base_url = settings.BACKEND_PUBLIC_BASE_URL.rstrip("/")
    return f"{base_url}/api/v1/connectors/oauth/callback/{type_key}"


def build_authorize_url(*, type_key: str, scopes: list[str], state: str) -> str:
    """The URL `initiate_connect` returns as `ConnectResult.redirect_url`.

    `access_type=offline` + `prompt=consent` together are what guarantee a
    `refresh_token` comes back on the token exchange - without `prompt=
    consent`, a user who has already granted this app access once before
    gets silently re-authorized with no `refresh_token` in the response at
    all (Google only issues one on the first-ever consent, or when forced).
    """
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID or "",
        "redirect_uri": oauth_redirect_uri(type_key),
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{settings.GOOGLE_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


def _stub_tokens(*, refresh_token: str | None = None, scope: str = "") -> GoogleTokenResult:
    return GoogleTokenResult(
        is_stub=True,
        detail="stub token (Google unreachable or not configured)",
        access_token=f"stub-access-token-{uuid.uuid4().hex[:12]}",
        refresh_token=refresh_token or f"stub-refresh-token-{uuid.uuid4().hex[:12]}",
        expires_at=time.time() + 3600,
        scope=scope,
        token_type="Bearer",
    )


def _token_result_from_response(data: dict[str, Any], *, fallback_refresh_token: str | None) -> GoogleTokenResult:
    """`data` is Google's raw token-endpoint JSON. `refresh_token` is absent
    on a refresh-grant response - `fallback_refresh_token` (the caller's
    already-stored one) is what keeps it from being lost."""
    return GoogleTokenResult(
        is_stub=False,
        detail=None,
        access_token=data["access_token"],
        refresh_token=data.get("refresh_token") or fallback_refresh_token,
        expires_at=time.time() + float(data.get("expires_in", 3600)),
        scope=data.get("scope"),
        token_type=data.get("token_type", "Bearer"),
    )


async def exchange_code_for_tokens(*, type_key: str, code: str) -> GoogleTokenResult:
    """Authorization-code -> token exchange, called from `handle_oauth_callback`.

    Raises `ValueError` on a real rejection from Google (expired/invalid
    code, redirect_uri mismatch) - never silently stubbed, since that would
    mask a genuine misconfiguration (e.g. `redirect_uri` not registered).
    """
    if not settings.google_configured:
        logger.warning(
            "[google-oauth] GOOGLE_CLIENT_ID/SECRET not configured - stub mode: fabricating a token "
            "pair for %s so the connect lifecycle stays testable offline.",
            type_key,
        )
        return _stub_tokens()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.GOOGLE_OAUTH_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": oauth_redirect_uri(type_key),
                },
            )
        if response.status_code in (400, 401):
            raise ValueError(f"Google rejected this authorization code: {response.text}")
        response.raise_for_status()
        return _token_result_from_response(response.json(), fallback_refresh_token=None)
    except _NETWORK_UNREACHABLE_ERRORS as exc:
        logger.warning(
            "[google-oauth] could not reach %s (%s) - stub mode: fabricating a token pair for %s "
            "so the connect lifecycle stays testable offline.",
            settings.GOOGLE_OAUTH_TOKEN_URL, exc, type_key,
        )
        return _stub_tokens()


async def refresh_access_token(*, refresh_token: str) -> GoogleTokenResult:
    """Refresh-token grant. Raises `ValueError` if Google reports the
    refresh token itself as invalid/revoked (the tenant must reconnect -
    callers surface this as `ConnectorState.ACTION_REQUIRED`, not a stub)."""
    if not settings.google_configured or refresh_token.startswith("stub-refresh-token-"):
        return _stub_tokens(refresh_token=refresh_token)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.GOOGLE_OAUTH_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
            )
        if response.status_code in (400, 401):
            try:
                error = response.json().get("error")
            except ValueError:
                error = None
            if error == "invalid_grant":
                raise GoogleReconnectRequired()
            # A client configuration error is different from a revoked grant.
            raise ValueError(f"Google token refresh failed (HTTP {response.status_code}, {error or 'unknown error'})")
        response.raise_for_status()
        return _token_result_from_response(response.json(), fallback_refresh_token=refresh_token)
    except _NETWORK_UNREACHABLE_ERRORS as exc:
        # Never replace a real stored credential with fabricated tokens on a
        # transient outage. Let the workflow's normal retry policy recover.
        logger.warning("[google-oauth] token refresh unavailable: %s", type(exc).__name__)
        raise


async def revoke_token(*, token: str) -> None:
    """Best-effort revoke, called from each adapter's `disconnect`. Never
    raises - a token already revoked/expired, or this sandbox having no
    network, are both fine to just log and move on from (matches
    `whatsapp/adapter.py::disconnect`'s identical best-effort convention)."""
    if not settings.google_configured or token.startswith("stub-"):
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(settings.GOOGLE_OAUTH_REVOKE_URL, data={"token": token})
    except httpx.HTTPError as exc:
        logger.warning("[google-oauth] best-effort token revoke failed: %s", exc)


_NO_IDENTITY: dict[str, Any] = {"email": None, "name": None, "sub": None}


async def fetch_userinfo(*, access_token: str) -> tuple[bool, dict[str, Any]]:
    """`(is_stub, {"email": str, "name": str, "sub": str})` - the safe-field
    allowlist every Google adapter puts into `connected_identity`.

    A 401/403 here is an EXPECTED outcome, not a real error: every adapter
    requests the narrowest scope that still covers what it actually does
    (calendar.events / meetings.space.created - see each adapter's own
    module docstring on least-privilege scoping), and Google's userinfo
    endpoint requires an identity scope (openid/email/profile) that none
    of them request on purpose. A previous version raised `ValueError`
    here, which - since `handle_oauth_callback` calls this BEFORE
    persisting the real access/refresh tokens via `upsert_credential` -
    threw away an otherwise fully successful OAuth grant just because the
    cosmetic "connected as <email>" label couldn't be filled in. Degrade
    to no-identity instead: the tokens are still valid for what the
    connector actually needs, this only affects the display label.
    """
    if access_token.startswith("stub-access-token-"):
        return True, {"email": "dev-sandbox@example.com", "name": "fusion-flow Dev Sandbox", "sub": "stub-user"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                settings.GOOGLE_USERINFO_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
        if response.status_code in (401, 403):
            logger.info(
                "[google-oauth] userinfo rejected (%s) - likely no identity scope requested "
                "(least-privilege by design). Connection still proceeds without a display identity.",
                response.status_code,
            )
            return False, dict(_NO_IDENTITY)
        response.raise_for_status()
        data = response.json()
        return False, {"email": data.get("email"), "name": data.get("name"), "sub": data.get("id")}
    except _NETWORK_UNREACHABLE_ERRORS as exc:
        logger.warning(
            "[google-oauth] could not reach %s (%s) - stub mode: returning a canned identity.",
            settings.GOOGLE_USERINFO_URL, exc,
        )
        return True, {"email": "dev-sandbox@example.com", "name": "fusion-flow Dev Sandbox", "sub": "stub-user"}


async def get_valid_access_token(session: AsyncSession, *, instance: ConnectorInstance) -> str:
    """The one call every Google adapter's outbound API methods make first.

    Reads the stored credential, transparently refreshes (and re-persists)
    it if within `_EXPIRY_SKEW_SECONDS` of expiring, and returns a ready-
    to-use access token. A revoked grant marks the connector as requiring
    reconnection in the caller's transaction, including workflow calls that
    bypass the connector lifecycle service. OAuth reconnection clears it.
    """
    if instance.state == ConnectorState.ACTION_REQUIRED and instance.last_error_message == _RECONNECT_MESSAGE:
        raise GoogleReconnectRequired()
    secret = await connector_service.get_credential_secret(session, instance=instance)
    if secret is None:
        raise RuntimeError(f"no credential stored for connector instance {instance.id}")

    if float(secret.get("expires_at", 0)) - _EXPIRY_SKEW_SECONDS > time.time():
        return str(secret["access_token"])

    try:
        if not secret.get("refresh_token"):
            raise GoogleReconnectRequired()
        result = await refresh_access_token(refresh_token=secret["refresh_token"])
    except GoogleReconnectRequired:
        instance.state = ConnectorState.ACTION_REQUIRED
        instance.health_status = HealthStatus.DOWN
        instance.last_error_message = _RECONNECT_MESSAGE
        await session.flush()
        raise
    await connector_service.upsert_credential(
        session,
        instance=instance,
        secret={
            "access_token": result.access_token,
            "refresh_token": result.refresh_token,
            "expires_at": result.expires_at,
            "scope": result.scope,
            "token_type": result.token_type,
        },
    )
    return result.access_token
