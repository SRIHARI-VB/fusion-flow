"""WhatsApp Business Platform connector adapter (Meta Graph API).

`auth_mode="oauth"`: tenants connect via Meta's OAuth / Embedded Signup
dialog, not an API key. Real Meta app review + a live WABA sandbox are
required for the network calls below to actually succeed (plan Risk #1).
Every place a real Graph API call belongs is marked `TODO(meta-graph-api)`
with the exact endpoint shape from Meta's public docs. When
`ConnectorSettings.whatsapp_configured` is False - the default in this dev
environment, since `WHATSAPP_APP_ID`/`WHATSAPP_APP_SECRET` are unset - this
adapter takes a clearly-logged stub path instead of making the call, so the
full connect -> webhook -> disconnect lifecycle stays testable with zero
external dependencies.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from typing import Any, Mapping
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.connectors import base
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.config import get_connector_settings
from fusionflow.modules.connectors.models import (
    ConnectorEvent,
    ConnectorEventType,
    ConnectorInstance,
    ConnectorOAuthState,
    ConnectorState,
    ConnectorType,
    HealthStatus,
)

logger = logging.getLogger(__name__)
settings = get_connector_settings()

CONNECTOR_TYPE_KEY = "whatsapp"

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"display_name": {"type": "string"}},
}


class WhatsAppAdapter(base.ConnectorAdapter):
    connector_type_key = CONNECTOR_TYPE_KEY
    auth_mode = "oauth"
    config_schema = CONFIG_SCHEMA

    def _callback_url(self) -> str:
        base_url = settings.BACKEND_PUBLIC_BASE_URL.rstrip("/")
        return f"{base_url}/api/v1/connectors/oauth/callback/{CONNECTOR_TYPE_KEY}"

    async def initiate_connect(
        self,
        *,
        tenant_id: uuid.UUID,
        instance: ConnectorInstance,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> base.ConnectResult:
        oauth_state = await connector_service.create_oauth_state(
            session, tenant_id=tenant_id, instance=instance, redirect_context=params
        )

        if not settings.whatsapp_configured:
            logger.warning(
                "[whatsapp] WHATSAPP_APP_ID/WHATSAPP_APP_SECRET not configured - "
                "stub mode: skipping the real Meta OAuth dialog and returning a "
                "same-request 'connected' result so the lifecycle stays testable."
            )
            return await self._stub_connected_result()

        # TODO(meta-graph-api): this is Meta's OAuth for Business Login
        # dialog (the redirect flow Embedded Signup layers a JS SDK popup on
        # top of - since no browser JS runs on this backend, this adapter
        # builds the equivalent server-side redirect). Real shape per Meta's
        # public docs:
        #   GET https://www.facebook.com/v20.0/dialog/oauth
        #     ?client_id={WHATSAPP_APP_ID}
        #     &redirect_uri={callback_url}
        #     &state={oauth_state.state_token}
        #     &scope=whatsapp_business_management,whatsapp_business_messaging
        #     &response_type=code
        query = urlencode(
            {
                "client_id": settings.WHATSAPP_APP_ID,
                "redirect_uri": self._callback_url(),
                "state": oauth_state.state_token,
                "scope": "whatsapp_business_management,whatsapp_business_messaging",
                "response_type": "code",
            }
        )
        redirect_url = f"{settings.WHATSAPP_OAUTH_DIALOG_URL}?{query}"
        return base.ConnectResult(state=ConnectorState.CONNECTING, redirect_url=redirect_url)

    async def _stub_connected_result(self) -> base.ConnectResult:
        waba_id = f"stub-waba-{uuid.uuid4().hex[:8]}"
        phone_number_id = f"stub-phone-{uuid.uuid4().hex[:8]}"
        return base.ConnectResult(
            state=ConnectorState.CONNECTED,
            connected_identity={
                "display_phone_number": "+1 555-0100",
                "verified_name": "fusion-flow Dev Sandbox",
                "waba_id": waba_id,
            },
            provider_ref_ids={"waba_id": waba_id, "phone_number_id": phone_number_id},
            health_status=HealthStatus.HEALTHY,
        )

    async def handle_oauth_callback(
        self,
        *,
        oauth_state: ConnectorOAuthState,
        code: str,
        instance: ConnectorInstance,
        session: AsyncSession,
    ) -> base.ConnectResult:
        if not settings.whatsapp_configured:
            logger.warning(
                "[whatsapp] stub mode - fabricating a successful OAuth callback result for code=%s", code
            )
            result = await self._stub_connected_result()
            await connector_service.upsert_credential(
                session, instance=instance, secret={"access_token": f"stub-token-{code}"}
            )
            return result

        async with httpx.AsyncClient(base_url=settings.WHATSAPP_GRAPH_API_BASE_URL, timeout=15.0) as client:
            # TODO(meta-graph-api): exchange the OAuth `code` for a long-lived
            # access token.
            #   GET /oauth/access_token
            #     ?client_id={WHATSAPP_APP_ID}&client_secret={WHATSAPP_APP_SECRET}
            #     &redirect_uri={callback_url}&code={code}
            token_response = await client.get(
                "/oauth/access_token",
                params={
                    "client_id": settings.WHATSAPP_APP_ID,
                    "client_secret": settings.WHATSAPP_APP_SECRET,
                    "redirect_uri": self._callback_url(),
                    "code": code,
                },
            )
            token_response.raise_for_status()
            access_token = token_response.json()["access_token"]

            # TODO(meta-graph-api): resolve the shared WABA granted during
            # Embedded Signup and its phone number.
            #   GET /me/businesses?access_token={access_token}
            #   GET /{waba_id}/phone_numbers?fields=display_phone_number,verified_name
            waba_response = await client.get("/me/businesses", params={"access_token": access_token})
            waba_response.raise_for_status()
            waba_data = (waba_response.json().get("data") or [{}])[0]
            waba_id = waba_data.get("id", "unknown")

        await connector_service.upsert_credential(session, instance=instance, secret={"access_token": access_token})

        return base.ConnectResult(
            state=ConnectorState.CONNECTED,
            connected_identity={"waba_id": waba_id, "verified_name": waba_data.get("name")},
            provider_ref_ids={"waba_id": waba_id},
            health_status=HealthStatus.HEALTHY,
        )

    async def test_connection(self, *, instance: ConnectorInstance, session: AsyncSession) -> base.HealthResult:
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail="No credential stored")

        if not settings.whatsapp_configured or str(secret.get("access_token", "")).startswith("stub-token-"):
            logger.info("[whatsapp] stub mode - test_connection returning a synthetic healthy result")
            return base.HealthResult(health_status=HealthStatus.HEALTHY, detail="stub: assumed healthy")

        waba_id = (instance.provider_ref_ids or {}).get("waba_id")
        # TODO(meta-graph-api): GET /{waba_id}?fields=id - a cheap call that
        # fails if the stored access token was revoked or the WABA was
        # unlinked from our app.
        async with httpx.AsyncClient(base_url=settings.WHATSAPP_GRAPH_API_BASE_URL, timeout=10.0) as client:
            try:
                response = await client.get(
                    f"/{waba_id}", params={"fields": "id", "access_token": secret["access_token"]}
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                return base.HealthResult(health_status=HealthStatus.DOWN, detail=str(exc))
        return base.HealthResult(health_status=HealthStatus.HEALTHY)

    async def disconnect(self, *, instance: ConnectorInstance, session: AsyncSession) -> None:
        if not settings.whatsapp_configured:
            logger.info("[whatsapp] stub mode - skipping Graph API unsubscribe call")
            return
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return
        waba_id = (instance.provider_ref_ids or {}).get("waba_id")
        # TODO(meta-graph-api): DELETE /{waba_id}/subscribed_apps - revoke our
        # app's webhook subscription for this WABA. Best-effort: a token
        # already revoked by the user makes this 400, which is fine.
        async with httpx.AsyncClient(base_url=settings.WHATSAPP_GRAPH_API_BASE_URL, timeout=10.0) as client:
            try:
                await client.delete(
                    f"/{waba_id}/subscribed_apps", params={"access_token": secret["access_token"]}
                )
            except httpx.HTTPError as exc:
                logger.warning("[whatsapp] best-effort unsubscribe failed: %s", exc)

    async def send_text_message(
        self, *, instance: ConnectorInstance, to: str, body: str, session: AsyncSession
    ) -> None:
        """Send an outbound text message via the WhatsApp Cloud API.

        Called by the `send_whatsapp_message` workflow node executor. Follows
        the same stub-if-not-configured convention as every other real call
        in this file - see the module docstring.
        """
        if not settings.whatsapp_configured:
            logger.warning(
                "[whatsapp] WHATSAPP_APP_ID/WHATSAPP_APP_SECRET not configured - "
                "stub mode: skipping the real Graph API send-message call "
                "(instance=%s, to=%s, body=%r)",
                instance.id,
                to,
                body,
            )
            return

        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        phone_number_id = (instance.provider_ref_ids or {}).get("phone_number_id")
        if not phone_number_id:
            raise RuntimeError(f"connector instance {instance.id} has no phone_number_id on record")

        # TODO(meta-graph-api): send a text message via the WhatsApp Cloud API.
        #   POST /{phone_number_id}/messages
        #     Authorization: Bearer {access_token}
        #     {
        #       "messaging_product": "whatsapp",
        #       "recipient_type": "individual",
        #       "to": "{to}",
        #       "type": "text",
        #       "text": {"preview_url": false, "body": "{body}"}
        #     }
        async with httpx.AsyncClient(base_url=settings.WHATSAPP_GRAPH_API_BASE_URL, timeout=15.0) as client:
            response = await client.post(
                f"/{phone_number_id}/messages",
                headers={"Authorization": f"Bearer {secret['access_token']}"},
                json={
                    "messaging_product": "whatsapp",
                    "recipient_type": "individual",
                    "to": to,
                    "type": "text",
                    "text": {"preview_url": False, "body": body},
                },
            )
            response.raise_for_status()

    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
        """Meta's `X-Hub-Signature-256` scheme: HMAC-SHA256 over the raw
        body, keyed by the **App Secret** (app-level, shared by every WABA
        subscribed to our app - not a per-tenant secret)."""
        app_secret = settings.WHATSAPP_WEBHOOK_APP_SECRET or settings.WHATSAPP_APP_SECRET
        if not app_secret:
            logger.warning(
                "[whatsapp] no webhook app secret configured - accepting webhook unverified (dev only)"
            )
            return True
        signature_header = headers.get("x-hub-signature-256", "")
        if not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(app_secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        provided = signature_header[len("sha256=") :]
        return hmac.compare_digest(expected, provided)

    async def resolve_instance_for_webhook(
        self,
        *,
        raw_payload: bytes,
        headers: Mapping[str, str],
        query_params: Mapping[str, str],
        session: AsyncSession,
    ) -> ConnectorInstance | None:
        """Match the inbound WABA id (`entry[0].id`) against a stored instance.

        Cross-tenant by necessity: a Meta webhook carries no tenant/JWT, only
        the WABA id, and no `SET LOCAL app.current_tenant_id` has run on this
        connection. In production this lookup must run through a DB role
        granted `BYPASSRLS` scoped only to webhook ingestion (mirroring
        `require_platform_admin`'s separate admin-only role) - that second
        role is not provisioned in this dev environment; see this task's
        final report.
        """
        try:
            body = json.loads(raw_payload)
        except json.JSONDecodeError:
            return None
        entries = body.get("entry") or []
        if not entries:
            return None
        waba_id = entries[0].get("id")
        if not waba_id:
            return None

        rows = await session.execute(
            select(ConnectorInstance)
            .join(ConnectorType, ConnectorType.id == ConnectorInstance.connector_type_id)
            .where(
                ConnectorType.key == CONNECTOR_TYPE_KEY,
                ConnectorInstance.provider_ref_ids["waba_id"].astext == waba_id,
            )
        )
        return rows.scalars().first()

    @staticmethod
    def _extract_inbound_message(body: dict[str, Any]) -> dict[str, Any] | None:
        """Pull the first inbound user message out of a WhatsApp Cloud API
        webhook body, or return None if this webhook is a status callback
        (`.statuses`) or otherwise doesn't carry a `.messages` entry.

        Real shape (Meta docs):
          entry[0].changes[0].value.messages[0] = {
            "from": "<wa_id>", "id": "<message_id>", "timestamp": "...",
            "type": "text", "text": {"body": "..."}
          }
        """
        entries = body.get("entry") or []
        for entry in entries:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                messages = value.get("messages") or []
                if not messages:
                    continue
                message = messages[0]
                text_body = (message.get("text") or {}).get("body")
                return {
                    "from": message.get("from"),
                    "message_id": message.get("id"),
                    "message_type": message.get("type"),
                    "text": text_body,
                    "timestamp": message.get("timestamp"),
                }
        return None

    async def handle_webhook(
        self,
        *,
        instance: ConnectorInstance,
        raw_payload: bytes,
        headers: Mapping[str, str],
        session: AsyncSession,
    ) -> list[ConnectorEvent]:
        try:
            body = json.loads(raw_payload)
        except json.JSONDecodeError:
            body = {"raw": raw_payload.decode("utf-8", errors="replace")}

        event = ConnectorEvent(
            id=uuid.uuid4(),
            tenant_id=instance.tenant_id,
            connector_instance_id=instance.id,
            event_type=ConnectorEventType.WEBHOOK_RECEIVED,
            payload=body,
        )
        session.add(event)
        await session.flush()

        inbound_message = self._extract_inbound_message(body)
        if inbound_message is not None:
            # Deferred import: `modules.workflows` (package __init__) imports
            # its built-in nodes, one of which (`send_whatsapp_message`)
            # imports *this* module for the `adapter` singleton - importing
            # `event_bus` at module level here would be a circular import.
            from fusionflow.modules.workflows.engine import event_bus

            # Same transaction/session as the ConnectorEvent write above -
            # the outbox row and the audit row commit together or not at
            # all (transactional outbox, see event_bus.py). The caller
            # (webhooks.py) commits once after this returns.
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="whatsapp.message_received",
                payload=inbound_message,
                connector_instance_id=instance.id,
            )

        return [event]


adapter = WhatsAppAdapter()
base.registry.register(adapter)
