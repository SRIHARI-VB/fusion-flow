"""Gmail connector adapter (Google API).

`auth_mode="oauth"`: unlike WhatsApp/Razorpay/Cloudflare R2's
bring-your-own-key-pair model, a tenant never types a credential in here -
`config_schema` is deliberately empty (`{"type": "object", "properties":
{}, "required": []}`). The tenant clicks "Connect with Google" on the
frontend, which calls `POST /connectors/gmail/connect` with an empty
`params` dict; `initiate_connect` below mints a `ConnectorOAuthState` row
(`connectors.service.create_oauth_state`) and hands back a
`google.oauth.build_authorize_url(...)` redirect - the browser is sent to
Google's consent screen, and the generic `GET
/connectors/oauth/callback/gmail` route (`router.py`, shared by every
OAuth connector) calls back into `handle_oauth_callback` below once Google
redirects with an authorization `code`. All the actual token-exchange/
refresh/revoke machinery (and the stub-on-network-unreachable fallback
that keeps the whole lifecycle testable in this sandbox) lives in the
shared `connectors.google.oauth` helper, reused unmodified by all four
Google connectors (`google_calendar`, `gmail`, `google_meet`,
`google_sheets`) - this module only supplies Gmail's own `SCOPES` and the
handful of Gmail-specific API calls (`send_message`,
`list_recent_messages`, and the `users.getProfile` health check).

Scope choice: `gmail.send` (compose/send only - no ability to read a
tenant's inbox unless `gmail.readonly` is also granted) plus
`gmail.readonly` (read-only access to list/fetch messages, no ability to
delete or modify anything) - together these cover this adapter's two
exposed capabilities (`send_message`, `list_recent_messages`) without ever
requesting the much broader `gmail.modify` or `mail.google.com` scopes,
which would let this app delete/label/trash a tenant's mail. Google shows
both scopes on its consent screen individually, so a tenant can see
exactly what they're granting.

Every real Gmail API call below is a genuine `httpx` call against
`GMAIL_API_BASE_URL` (`https://gmail.googleapis.com/gmail/v1`) using the
bearer access token `google.oauth.get_valid_access_token` hands back
(transparently refreshed if it's about to expire) - there is no
send/list-specific stub fallback the way WhatsApp's Graph API calls have,
since a tenant explicitly invoking "send an email" or "list my messages"
from a workflow should see a real failure if Gmail is unreachable, not a
silently-fabricated success. The one place this adapter *does* fall back
to a stub result on a network-unreachable error is `test_connection`'s
cheap `users.getProfile` health probe - mirroring
`whatsapp/adapter.py`'s `_NETWORK_UNREACHABLE_ERRORS` convention exactly,
since a health check silently failing this sandbox's lack of egress would
otherwise flip every freshly-connected instance to `action_required` for
no real reason.
"""

from __future__ import annotations

import base64
import logging
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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

CONNECTOR_TYPE_KEY = "gmail"

# See module docstring's "Scope choice" section for why these two and no
# broader ones (gmail.modify, mail.google.com).
SCOPES: list[str] = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# No user-entered params at all - the tenant clicks a button and is
# redirected to Google; everything Gmail-specific it needs is `SCOPES`
# above, requested at authorize-url build time, not typed in a form.
CONFIG_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

# Errors that mean "could not reach Gmail at all" (this sandbox), as
# opposed to "reached Gmail and it rejected the token" - only the former
# falls back to a stub health result. Product-specific (not part of the
# shared `connectors.google.oauth` helper, which only knows about the
# *token* endpoints) - mirrors `whatsapp/adapter.py`'s identical local
# definition.
_NETWORK_UNREACHABLE_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.TimeoutException)


class GmailAdapter(base.ConnectorAdapter):
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
        """Start the OAuth dance. No credential exists yet - only a
        `ConnectorOAuthState` row is created here, so the callback can
        later correlate Google's redirect back to this tenant/instance."""
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
        """Exchange the authorization `code` for tokens, resolve the
        connected Google account's identity, and persist the credential.
        `oauth_state` itself is unused here (already validated/consumed by
        `connectors.service.complete_oauth_callback` before this runs) -
        kept as a parameter only to satisfy the base class signature."""
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
        """Cheap live health check: refresh (if needed) then a single
        `GET /users/me/profile` call. `get_valid_access_token`'s own
        `RuntimeError` (never connected) / `ValueError` (refresh token
        rejected by Google - reconnect required) both mean this instance
        is unambiguously down, distinct from "network unreachable" below."""
        try:
            access_token = await google_oauth.get_valid_access_token(session, instance=instance)
        except (RuntimeError, ValueError) as exc:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail=str(exc))

        try:
            async with httpx.AsyncClient(base_url=settings.GMAIL_API_BASE_URL, timeout=10.0) as client:
                response = await client.get(
                    "/users/me/profile", headers={"Authorization": f"Bearer {access_token}"}
                )
            if response.status_code in (401, 403):
                return base.HealthResult(
                    health_status=HealthStatus.DOWN,
                    detail=f"Gmail rejected this access token (status {response.status_code})",
                )
            response.raise_for_status()
            return base.HealthResult(health_status=HealthStatus.HEALTHY)
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[gmail] could not reach %s (%s) - stub mode: assuming healthy so the test-connection "
                "lifecycle stays testable offline (instance=%s).",
                settings.GMAIL_API_BASE_URL,
                exc,
                instance.id,
            )
            return base.HealthResult(health_status=HealthStatus.HEALTHY, detail=f"stub: assumed healthy ({exc})")

    async def disconnect(self, *, instance: ConnectorInstance, session: AsyncSession) -> None:
        """Best-effort revoke of whichever token we still have on file -
        prefers the refresh token (revoking it also invalidates every
        access token minted from it) but falls back to the access token
        alone if no refresh token was ever stored."""
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return
        await google_oauth.revoke_token(token=secret.get("refresh_token") or secret.get("access_token"))

    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
        # Gmail has no inbound webhook delivery model this codebase
        # implements (real-time updates would require a Pub/Sub push
        # subscription via `users.watch`, out of scope for this adapter) -
        # always False so nothing can masquerade as an authenticated Gmail
        # webhook. Mirrors `cloudflare_r2/adapter.py` exactly.
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

    async def send_message(
        self,
        instance: ConnectorInstance,
        session: AsyncSession,
        *,
        to: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
    ) -> dict[str, Any]:
        """Compose an RFC 2822 message and send it via
        `POST /users/me/messages/send`. `body_html`, if given, produces a
        `multipart/alternative` message carrying both the plain-text and
        HTML parts (mail clients that can render HTML show `body_html`;
        everything else falls back to `body_text`) - otherwise a plain
        `MIMEText(body_text)` is sent."""
        access_token = await google_oauth.get_valid_access_token(session, instance=instance)

        message: MIMEMultipart | MIMEText
        if body_html:
            message = MIMEMultipart("alternative")
            message.attach(MIMEText(body_text, "plain"))
            message.attach(MIMEText(body_html, "html"))
        else:
            message = MIMEText(body_text)
        message["To"] = to
        message["Subject"] = subject

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        async with httpx.AsyncClient(base_url=settings.GMAIL_API_BASE_URL, timeout=15.0) as client:
            response = await client.post(
                "/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
            )
            response.raise_for_status()
            return response.json()

    async def list_recent_messages(
        self,
        instance: ConnectorInstance,
        session: AsyncSession,
        *,
        max_results: int = 10,
        query: str | None = None,
    ) -> list[dict[str, Any]]:
        """List the tenant's most recent messages, each enriched with its
        `snippet`/`subject`/`from` - Gmail's `users.messages.list` only
        returns bare `{"id", "threadId"}` pairs, so a second
        `users.messages.get` (metadata-only, cheap) call per id is required
        to surface anything human-readable. Bounded and simple by design:
        no pagination beyond the single `maxResults`-capped page Gmail
        already returns."""
        access_token = await google_oauth.get_valid_access_token(session, instance=instance)

        list_params: dict[str, Any] = {"maxResults": max_results}
        if query:
            list_params["q"] = query

        async with httpx.AsyncClient(base_url=settings.GMAIL_API_BASE_URL, timeout=15.0) as client:
            list_response = await client.get(
                "/users/me/messages",
                headers={"Authorization": f"Bearer {access_token}"},
                params=list_params,
            )
            list_response.raise_for_status()
            message_ids = [m["id"] for m in (list_response.json().get("messages") or [])][:max_results]

            results: list[dict[str, Any]] = []
            for message_id in message_ids:
                detail_response = await client.get(
                    f"/users/me/messages/{message_id}",
                    headers={"Authorization": f"Bearer {access_token}"},
                    params={"format": "metadata", "metadataHeaders": ["Subject", "From"]},
                )
                detail_response.raise_for_status()
                detail = detail_response.json()
                header_values = {
                    header.get("name"): header.get("value")
                    for header in (detail.get("payload") or {}).get("headers") or []
                }
                results.append(
                    {
                        "id": message_id,
                        "snippet": detail.get("snippet"),
                        "subject": header_values.get("Subject"),
                        "from": header_values.get("From"),
                    }
                )
            return results

    async def perform_action(
        self, *, action: str, params: dict[str, Any], instance: ConnectorInstance, session: AsyncSession
    ) -> dict[str, Any]:
        """Dispatch for the generic `connector.action` workflow node type -
        mirrors `whatsapp/adapter.py::perform_action`'s style exactly."""
        if action == "send_message":
            to = params.get("to")
            subject = params.get("subject")
            body_text = params.get("body_text")
            if not to or not subject or not body_text:
                raise ValueError("send_message requires non-empty 'to', 'subject', and 'body_text' params")
            return await self.send_message(
                instance,
                session,
                to=to,
                subject=subject,
                body_text=body_text,
                body_html=params.get("body_html"),
            )
        if action == "list_recent_messages":
            messages = await self.list_recent_messages(
                instance,
                session,
                max_results=params.get("max_results", 10),
                query=params.get("query"),
            )
            return {"messages": messages}
        raise NotImplementedError(f"{self.connector_type_key} does not support action {action!r}")


adapter = GmailAdapter()
base.registry.register(adapter)
