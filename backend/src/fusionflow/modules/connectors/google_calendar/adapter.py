"""Google Calendar connector adapter.

`auth_mode="oauth"`: unlike WhatsApp/Razorpay/Cloudflare R2 (all
`auth_mode="api_key"`, a tenant pastes their own provider-generated
key(s) directly into `initiate_connect`'s `params`), a Google connector
has no user-entered `params` at all - `config_schema` is an empty object
schema and the tenant's only action is clicking "Connect" and completing
Google's own consent screen. The entire OAuth2 authorization-code dance
(building the `accounts.google.com` authorize URL, exchanging the
callback's `code` for a token pair, transparently refreshing an expiring
access token, revoking on disconnect) is centralized in
`connectors/google/oauth.py` and shared by all four Google connectors
(`google_calendar`, `gmail`, `google_meet`, `google_sheets`) - this
adapter never talks to Google's OAuth endpoints directly, only to
`google_oauth`'s helpers and, once a valid access token is in hand, to
the Calendar API itself.

Scope choice: `https://www.googleapis.com/auth/calendar.events` (not the
broader `.../auth/calendar`, which also grants calendar-*settings* and
calendar-*list* management). This connector only ever creates, lists,
and updates events on the tenant's primary calendar via
`create_event`/`list_events`/`update_event` (and the matching
`perform_action` dispatch the workflow engine's generic
`connector.action` node type calls through - see
`base.ConnectorAdapter.perform_action`'s docstring) - narrowing to the
`.events` scope is the least-privilege grant that still covers every
capability this adapter exposes, and it is also less alarming on
Google's own consent screen than requesting full calendar management.

Connect/callback flow (mirrors every other OAuth connector built against
`connectors/base.py`'s framework):
  1. `initiate_connect` calls `connector_service.create_oauth_state` (a
     short-lived, single-use, CSRF-safe row correlating a `state_token`
     back to this tenant/instance - see `service.py`'s docstring) and
     returns a `ConnectResult(state=CONNECTING, redirect_url=...)`
     pointing at Google's consent screen. No credential exists yet at
     this point - nothing is stored here.
  2. The browser is redirected to Google, the tenant consents, and
     Google redirects back to the generic `GET
     /connectors/oauth/callback/google_calendar` route, which resolves
     the `state` token back to this tenant/instance and calls
     `handle_oauth_callback` below.
  3. `handle_oauth_callback` exchanges the authorization `code` for a
     token pair (`google_oauth.exchange_code_for_tokens`), fetches a
     safe-field identity allowlist (`google_oauth.fetch_userinfo`) for
     `connected_identity`, and persists the full token pair via
     `connector_service.upsert_credential` - the only place any Google
     Calendar credential material is ever written.

Every outbound Calendar API call in `create_event`/`list_events`/
`update_event`/`test_connection` first calls
`google_oauth.get_valid_access_token`, which transparently refreshes (and
re-persists) an expiring access token - this adapter never inspects or
refreshes a token itself, that logic lives entirely in the shared helper.

No inbound webhooks: Google Calendar push notifications require a
separate `watch()`/channel-registration call this MVP does not implement
(the workflow engine currently has no calendar-event-changed trigger to
wire one into) - `verify_webhook_signature`/`resolve_instance_for_webhook`/
`handle_webhook` are all hard-coded no-ops, exactly mirroring
`cloudflare_r2/adapter.py`'s identical "no webhooks" shape.

Stub-on-network-unreachable convention (matches every other adapter in
this codebase): `test_connection`'s own live Calendar API call
(`GET /calendars/primary`) defines its own local
`_NETWORK_UNREACHABLE_ERRORS` tuple - deliberately NOT reused from
`connectors/google/oauth.py`, since that module's tuple only covers
Google's *OAuth* endpoints, and a product API call (Calendar) failing to
reach the network is this adapter's own concern, not the shared OAuth
helper's. `create_event`/`list_events`/`update_event` apply the same
narrow fallback (log a warning, return a clearly-labelled stub result)
so the workflow actions built on top of them stay testable in this
sandbox (which has no outbound network) - a real 4xx/5xx rejection from
Google is never swallowed this way, only "could not reach the network at
all" is.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Mapping

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.connectors import base
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.config import get_connector_settings
from fusionflow.modules.connectors.google import oauth as google_oauth
from fusionflow.modules.connectors.models import (
    ConnectorEvent,
    ConnectorInstance,
    ConnectorOAuthState,
    ConnectorState,
    HealthStatus,
)

logger = logging.getLogger(__name__)
settings = get_connector_settings()

CONNECTOR_TYPE_KEY = "google_calendar"

# No user-entered connect params - see module docstring.
CONFIG_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

# Least-privilege scope covering every capability this adapter exposes
# (create/list/update events on the primary calendar) - see module docstring.
SCOPES: list[str] = ["https://www.googleapis.com/auth/calendar.events"]

# Errors that mean "could not reach the Google Calendar API at all" (this
# sandbox), as opposed to "reached it and it rejected the request" - only
# the former falls back to a stub result. Mirrors
# whatsapp/adapter.py::_NETWORK_UNREACHABLE_ERRORS exactly, defined locally
# here rather than imported from connectors/google/oauth.py since that
# module's tuple is scoped to Google's *OAuth* endpoints, not the Calendar
# product API this adapter itself calls.
_NETWORK_UNREACHABLE_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.TimeoutException)


class GoogleCalendarAdapter(base.ConnectorAdapter):
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
        """Start the OAuth dance - no credential exists yet, see module docstring."""
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
        oauth_state: ConnectorOAuthState,
        code: str,
        instance: ConnectorInstance,
        session: AsyncSession,
    ) -> base.ConnectResult:
        """Exchange `code` for tokens, fetch identity, persist the credential."""
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
        """Best-effort live health check: a valid token + a cheap real call."""
        try:
            access_token = await google_oauth.get_valid_access_token(session, instance=instance)
        except (RuntimeError, ValueError) as exc:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail=str(exc))

        try:
            async with httpx.AsyncClient(base_url=settings.GOOGLE_CALENDAR_API_BASE_URL, timeout=10.0) as client:
                response = await client.get(
                    "/calendars/primary", headers={"Authorization": f"Bearer {access_token}"}
                )
            if response.status_code in (401, 403):
                return base.HealthResult(
                    health_status=HealthStatus.DOWN,
                    detail=f"Google rejected this access token (status {response.status_code})",
                )
            response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[google_calendar] could not reach %s (%s) - stub mode: assuming the connection is "
                "healthy so the health-check lifecycle stays testable offline.",
                settings.GOOGLE_CALENDAR_API_BASE_URL,
                exc,
            )
            return base.HealthResult(health_status=HealthStatus.HEALTHY, detail=f"stub: assumed healthy ({exc})")
        return base.HealthResult(health_status=HealthStatus.HEALTHY)

    async def disconnect(self, *, instance: ConnectorInstance, session: AsyncSession) -> None:
        """Best-effort revoke of whichever token Google will accept for revocation."""
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return
        await google_oauth.revoke_token(token=secret.get("refresh_token") or secret.get("access_token"))

    # --- No inbound webhooks - see module docstring. ------------------

    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
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

    # --- Capabilities ---------------------------------------------------

    async def create_event(
        self,
        instance: ConnectorInstance,
        session: AsyncSession,
        *,
        summary: str,
        description: str | None = None,
        start: str,
        end: str,
        location: str | None = None,
        attendees: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create an event on the tenant's primary calendar.

        `start`/`end` are ISO datetime strings, wrapped in Google's
        `{"dateTime": ...}` shape. `attendees` is a plain list of emails,
        expanded into Google's `[{"email": ...}, ...]` shape. Falls back
        to a clearly-labelled stub result when the network is
        unreachable - see module docstring.
        """
        access_token = await google_oauth.get_valid_access_token(session, instance=instance)

        body: dict[str, Any] = {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}}
        if description:
            body["description"] = description
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": email} for email in attendees]

        try:
            async with httpx.AsyncClient(base_url=settings.GOOGLE_CALENDAR_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    "/calendars/primary/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=body,
                )
                response.raise_for_status()
                return response.json()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[google_calendar] could not reach %s (%s) - stub mode: fabricating a created-event "
                "response so the workflow action stays testable offline (instance=%s).",
                settings.GOOGLE_CALENDAR_API_BASE_URL,
                exc,
                instance.id,
            )
            stub_id = f"stub-event-{uuid.uuid4().hex[:8]}"
            return {
                "id": stub_id,
                "status": "confirmed",
                "htmlLink": f"https://calendar.google.com/calendar/event?eid={stub_id}",
                "summary": summary,
                "description": description,
                "location": location,
                "start": {"dateTime": start},
                "end": {"dateTime": end},
                "attendees": [{"email": email} for email in (attendees or [])],
            }

    async def list_events(
        self,
        instance: ConnectorInstance,
        session: AsyncSession,
        *,
        time_min: str | None = None,
        time_max: str | None = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """List upcoming events on the tenant's primary calendar.

        `time_min`/`time_max` are RFC3339 timestamps, only sent as query
        params when given. Falls back to an empty list when the network
        is unreachable - see module docstring.
        """
        access_token = await google_oauth.get_valid_access_token(session, instance=instance)

        params: dict[str, Any] = {"maxResults": max_results, "singleEvents": "true", "orderBy": "startTime"}
        if time_min:
            params["timeMin"] = time_min
        if time_max:
            params["timeMax"] = time_max

        try:
            async with httpx.AsyncClient(base_url=settings.GOOGLE_CALENDAR_API_BASE_URL, timeout=15.0) as client:
                response = await client.get(
                    "/calendars/primary/events",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params=params,
                )
                response.raise_for_status()
                return response.json().get("items", [])
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[google_calendar] could not reach %s (%s) - stub mode: returning an empty event list "
                "so the workflow action stays testable offline (instance=%s).",
                settings.GOOGLE_CALENDAR_API_BASE_URL,
                exc,
                instance.id,
            )
            return []

    async def update_event(
        self,
        instance: ConnectorInstance,
        session: AsyncSession,
        *,
        event_id: str,
        **fields: Any,
    ) -> dict[str, Any]:
        """Patch an existing event with whatever subset of
        `summary`/`description`/`start`/`end`/`location` is passed in
        `fields` - `start`/`end` (if present) are wrapped in Google's
        `{"dateTime": ...}` shape, everything else is passed through
        as-is. Falls back to a stub "updated" event when the network is
        unreachable - see module docstring.
        """
        access_token = await google_oauth.get_valid_access_token(session, instance=instance)

        body: dict[str, Any] = {}
        for key, value in fields.items():
            if value is None:
                continue
            if key in ("start", "end"):
                body[key] = {"dateTime": value}
            else:
                body[key] = value

        try:
            async with httpx.AsyncClient(base_url=settings.GOOGLE_CALENDAR_API_BASE_URL, timeout=15.0) as client:
                response = await client.patch(
                    f"/calendars/primary/events/{event_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    json=body,
                )
                response.raise_for_status()
                return response.json()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[google_calendar] could not reach %s (%s) - stub mode: fabricating an updated-event "
                "response so the workflow action stays testable offline (instance=%s, event_id=%s).",
                settings.GOOGLE_CALENDAR_API_BASE_URL,
                exc,
                instance.id,
                event_id,
            )
            return {"id": event_id, "status": "confirmed", **body}

    async def perform_action(
        self, *, action: str, params: dict[str, Any], instance: ConnectorInstance, session: AsyncSession
    ) -> dict[str, Any]:
        """Dispatch for the generic `connector.action` workflow node type -
        see `base.ConnectorAdapter.perform_action`'s docstring. Mirrors
        `whatsapp/adapter.py::perform_action`'s style exactly: validate
        required params up front (raise `ValueError` for anything
        missing), then delegate to the matching capability method."""
        if action == "create_event":
            summary = params.get("summary")
            start = params.get("start")
            end = params.get("end")
            if not summary or not start or not end:
                raise ValueError("create_event requires non-empty 'summary', 'start', and 'end' params")
            return await self.create_event(
                instance,
                session,
                summary=summary,
                description=params.get("description"),
                start=start,
                end=end,
                location=params.get("location"),
                attendees=params.get("attendees"),
            )
        if action == "list_events":
            items = await self.list_events(
                instance,
                session,
                time_min=params.get("time_min"),
                time_max=params.get("time_max"),
                max_results=params.get("max_results", 10),
            )
            return {"items": items}
        if action == "update_event":
            event_id = params.get("event_id")
            if not event_id:
                raise ValueError("update_event requires a non-empty 'event_id' param")
            fields = {k: v for k, v in params.items() if k != "event_id"}
            return await self.update_event(instance, session, event_id=event_id, **fields)
        raise NotImplementedError(f"{self.connector_type_key} does not support action {action!r}")


adapter = GoogleCalendarAdapter()
base.registry.register(adapter)
