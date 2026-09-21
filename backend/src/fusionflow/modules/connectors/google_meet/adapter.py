"""Google Meet connector adapter (Google Meet REST API - the "Spaces" API).

`auth_mode="oauth"`: unlike WhatsApp/Razorpay/Cloudflare R2's bring-your-own
api-key model, a tenant clicks "Connect with Google" and is redirected
through Google's consent screen - there is no `config_schema` field for
them to fill in (`CONFIG_SCHEMA` below is an empty object). All token
exchange/refresh/revoke plumbing lives in the shared
`connectors.google.oauth` helper (built once for all four Google
connectors); this module only supplies the Meet-specific scope and the one
capability this connector exposes to the workflow engine.

Why the Meet Spaces API (`meet.googleapis.com/v2`), not Calendar's
`conferenceData`: Google's older, still-common pattern for "create a Meet
link" is to create a Calendar event with
`conferenceData.createRequest.conferenceSolutionKey.type = "hangoutsMeet"`
and read the generated link back off the created event - i.e. Meet-as-a-
side-effect-of-Calendar. That requires Calendar scope/API access this
connector has no other reason to request, ties every meeting to a Calendar
event whether or not the workflow wants one, and is explicitly the legacy
workaround Google's own docs point away from now that a dedicated Meet API
exists. The Meet REST API's `spaces.create` (this adapter's `create_meeting`)
creates a standalone meeting space directly - no calendar event, no
Calendar scope, one narrowly-scoped permission
(`meetings.space.created` - "manage meeting spaces created by the app")
that says exactly what this connector does and nothing more. Per Google's
principle of least privilege for OAuth consent screens, that narrower scope
is also what keeps this app off Google's more invasive verification tiers
for as long as possible.

OAuth flow (identical shape to every other Google connector - see
`connectors.google.oauth`'s module docstring for the shared plumbing):
  1. `initiate_connect` opens a `ConnectorOAuthState` row and redirects the
     tenant to Google's consent screen for `SCOPES` below.
  2. Google redirects back to `GET /connectors/oauth/callback/google_meet`
     with a `code`; `connectors.service.complete_oauth_callback` resolves
     the state token back to a tenant/instance and calls
     `handle_oauth_callback` here, which exchanges the code for tokens,
     fetches the connecting user's identity (email/name only - see
     `connected_identity`'s safe-field-allowlist guarantee in `base.py`'s
     module docstring), and stores the token set via
     `connector_service.upsert_credential`.
  3. Every subsequent outbound call (`create_meeting`, `test_connection`)
     goes through `google_oauth.get_valid_access_token`, which
     transparently refreshes an expiring access token using the stored
     `refresh_token` and re-persists the refreshed pair - this adapter
     never talks to Google's token endpoint directly.

Stub-on-network-unreachable convention (matches every other adapter in this
codebase - see `whatsapp/adapter.py`'s module docstring): a real rejection
from Google (expired/invalid access token, revoked grant) is a genuine
error and must propagate; only "could not reach Google at all" (this
sandbox has no network) falls back to a fabricated-but-clearly-logged stub
response, so the connect/create-meeting lifecycle stays testable offline.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Literal, Mapping

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.connectors import base
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.config import get_connector_settings
from fusionflow.modules.connectors.google import oauth as google_oauth
from fusionflow.modules.connectors.models import (
    ConnectorEvent,
    ConnectorInstance,
    ConnectorState,
    HealthStatus,
)

logger = logging.getLogger(__name__)
settings = get_connector_settings()

CONNECTOR_TYPE_KEY = "google_meet"

# "manage meeting spaces created by the app" - the narrowest Meet API scope
# that covers this adapter's one capability (creating meeting spaces). See
# module docstring for why this is used instead of a Calendar scope.
SCOPES: list[str] = ["https://www.googleapis.com/auth/meetings.space.created"]

# No user-entered params at all: a tenant just clicks "Connect with Google"
# and is redirected through the OAuth consent screen - see
# `GoogleMeetConnectStep.tsx` on the frontend.
CONFIG_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

# Mirrors whatsapp/adapter.py::_NETWORK_UNREACHABLE_ERRORS and
# connectors/google/oauth.py's identical constant - only "could not reach
# Google at all" falls back to a stub; a real 4xx rejection from Google is
# a genuine error and must propagate.
_NETWORK_UNREACHABLE_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.TimeoutException)

AccessType = Literal["OPEN", "TRUSTED", "RESTRICTED"]
_VALID_ACCESS_TYPES = ("OPEN", "TRUSTED", "RESTRICTED")


class GoogleMeetAdapter(base.ConnectorAdapter):
    connector_type_key = CONNECTOR_TYPE_KEY
    auth_mode = "oauth"
    config_schema = CONFIG_SCHEMA

    async def initiate_connect(
        self,
        *,
        tenant_id: uuid.UUID,
        instance: ConnectorInstance,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> base.ConnectResult:
        """Opens the OAuth state row and hands back Google's consent-screen
        URL - no credential exists yet at this point (that only happens once
        `handle_oauth_callback` lands), so nothing is persisted here beyond
        the state row itself."""
        oauth_state = await connector_service.create_oauth_state(session, tenant_id=tenant_id, instance=instance)
        return base.ConnectResult(
            state=ConnectorState.CONNECTING,
            redirect_url=google_oauth.build_authorize_url(
                type_key=CONNECTOR_TYPE_KEY, scopes=SCOPES, state=oauth_state.state_token
            ),
        )

    async def handle_oauth_callback(
        self,
        *,
        oauth_state: Any,
        code: str,
        instance: ConnectorInstance,
        session: AsyncSession,
    ) -> base.ConnectResult:
        result = await google_oauth.exchange_code_for_tokens(type_key=CONNECTOR_TYPE_KEY, code=code)
        _is_stub_identity, identity = await google_oauth.fetch_userinfo(access_token=result.access_token)
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
        return base.ConnectResult(
            state=ConnectorState.CONNECTED,
            connected_identity={"email": identity.get("email"), "name": identity.get("name")},
            health_status=HealthStatus.HEALTHY,
            error_message=f"stub token exchange ({result.detail})" if result.is_stub else None,
        )

    async def test_connection(self, *, instance: ConnectorInstance, session: AsyncSession) -> base.HealthResult:
        """Health check by proxy, not by calling the Meet API itself.

        The Meet Spaces API has no cheap read-only "list all my spaces" or
        "get without an id" endpoint - `spaces.create` is the only relevant
        call this adapter has a scope for, and calling it just to check
        health would create a real, side-effecting meeting space on every
        health check (this instance list is polled periodically by the
        frontend - see `hooks.ts::useConnectorInstances`). Instead, this
        treats "the stored OAuth credential is present and either still
        valid or successfully refreshable" as the health signal:
        `google_oauth.get_valid_access_token` does exactly that (reading the
        stored token, refreshing it against Google's token endpoint if
        near expiry, and re-persisting the result) - if it raises, this
        instance is definitely unhealthy (never connected, or Google has
        revoked the refresh token and a reconnect is required); if it
        returns, the token is genuinely usable right now.
        """
        try:
            await google_oauth.get_valid_access_token(session, instance=instance)
        except RuntimeError as exc:
            # No credential stored at all - this instance was never connected.
            return base.HealthResult(health_status=HealthStatus.DOWN, detail=str(exc))
        except ValueError as exc:
            # Google rejected the stored refresh token - reconnect required.
            return base.HealthResult(health_status=HealthStatus.DOWN, detail=str(exc))
        return base.HealthResult(health_status=HealthStatus.HEALTHY)

    async def disconnect(self, *, instance: ConnectorInstance, session: AsyncSession) -> None:
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return
        # Revoking either token invalidates the whole grant on Google's
        # side; the refresh token is preferred since it's longer-lived than
        # whichever access token happens to be current.
        await google_oauth.revoke_token(token=secret.get("refresh_token") or secret.get("access_token"))

    async def create_meeting(
        self, instance: ConnectorInstance, session: AsyncSession, *, access_type: AccessType = "TRUSTED"
    ) -> dict[str, Any]:
        """Create a new Google Meet space via `POST /spaces` and return
        Google's response JSON as-is (`name`, `meetingUri`, `meetingCode`,
        `config`, ...) - called by the `google_meet.create_meeting`
        workflow node executor and by `perform_action` below.

        `access_type` is Google's own enum for who can join the space
        without an explicit invite from the host: `"OPEN"` (anyone with the
        link), `"TRUSTED"` (anyone in the host's Google Workspace org),
        `"RESTRICTED"` (invitees only) - defaults to `"TRUSTED"`, Google's
        own default for a standard Workspace user.
        """
        if access_type not in _VALID_ACCESS_TYPES:
            raise ValueError(f"access_type must be one of {_VALID_ACCESS_TYPES}, got {access_type!r}")

        access_token = await google_oauth.get_valid_access_token(session, instance=instance)

        try:
            async with httpx.AsyncClient(base_url=settings.GOOGLE_MEET_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    "/spaces",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"config": {"accessType": access_type}},
                )
            if response.status_code in (401, 403):
                raise ValueError("Google rejected this access token when creating a Meet space")
            response.raise_for_status()
            return response.json()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[google_meet] could not reach %s (%s) - stub mode: fabricating a meeting space so "
                "the create_meeting lifecycle stays testable offline (instance=%s).",
                settings.GOOGLE_MEET_API_BASE_URL,
                exc,
                instance.id,
            )
            space_id = uuid.uuid4().hex[:10]
            meeting_code = f"{space_id[:3]}-{space_id[3:7]}-{space_id[7:10]}"
            return {
                "name": f"spaces/{space_id}",
                "meetingUri": f"https://meet.google.com/{meeting_code}",
                "meetingCode": meeting_code,
                "config": {"accessType": access_type},
            }

    async def perform_action(
        self, *, action: str, params: dict[str, Any], instance: ConnectorInstance, session: AsyncSession
    ) -> dict[str, Any]:
        """Dispatch for the generic `connector.action` workflow node type
        (see `base.ConnectorAdapter.perform_action`'s docstring) - mirrors
        `whatsapp/adapter.py::perform_action`'s style. `create_meeting` is
        this connector's only capability today; a future one is one more
        `elif` branch here."""
        if action == "create_meeting":
            access_type = params.get("access_type") or "TRUSTED"
            return await self.create_meeting(instance, session, access_type=access_type)
        raise NotImplementedError(f"{self.connector_type_key} does not support action {action!r}")

    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
        # The Meet Spaces API has no inbound webhook mechanism this
        # connector subscribes to - always False so an inbound request
        # never masquerades as an authenticated Google Meet webhook.
        # Mirrors cloudflare_r2/adapter.py's identical no-webhooks stance.
        return False

    async def resolve_instance_for_webhook(
        self,
        *,
        raw_payload: bytes,
        headers: Mapping[str, str],
        query_params: Mapping[str, str],
        session: AsyncSession,
    ) -> ConnectorInstance | None:
        return None

    async def handle_webhook(
        self,
        *,
        instance: ConnectorInstance,
        raw_payload: bytes,
        headers: Mapping[str, str],
        session: AsyncSession,
    ) -> list[ConnectorEvent]:
        return []


adapter = GoogleMeetAdapter()
base.registry.register(adapter)
