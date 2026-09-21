"""Facebook connector adapter (Meta Graph API - Page Messenger Platform).

`auth_mode="api_key"`: same BYO-credentials model as
`whatsapp/adapter.py` and `instagram/adapter.py`, not OAuth. Each tenant
generates their own Page access token in their own Meta Business Suite
(with `pages_messaging` permission) and pastes it here, alongside the
Facebook Page id it belongs to - there is no shared/platform Meta
Developer App and no OAuth dialog for the connect step itself, so this
works in any environment (including plain localhost dev) with no public
callback URL needed just to connect.

This adapter is a near-duplicate of `instagram/adapter.py` on purpose:
Facebook Pages and Instagram professional accounts both ride the same
Meta Graph API / Messenger Platform family, share the same webhook
envelope shape (`entry[]` keyed by a provider account id, `x-hub-
signature-256` HMAC signing), and the same BYO-Page-token connect model -
only the endpoint paths and payload field names differ (Facebook has no
comment-webhook field in this shape, so this adapter, unlike Instagram's,
only ever extracts inbound messages). See that module's docstring for the
fuller rationale this one intentionally mirrors line-for-line.

Every place a real Graph API call belongs is marked `TODO(meta-graph-api)`
with the exact endpoint shape from Meta's public docs. If that call cannot
even reach the network (this sandbox has none), the failure is caught
narrowly (`_NETWORK_UNREACHABLE_ERRORS`) and downgraded to a clearly-logged
stub result so the connect/send/disconnect lifecycle stays testable - an
actual rejection from Meta (bad token, bad page id, revoked access) is a
real error and is never swallowed, same convention as
`whatsapp/adapter.py`/`instagram/adapter.py`.

Per-tenant `webhook_verify_token` design rationale: Meta's GET webhook
verification handshake (`hub.verify_token`) carries no tenant identifier
at all, so a single fixed verify token - like `whatsapp/adapter.py` uses -
normally cannot vary per tenant; there would be no way to know *whose*
token to check it against. What makes a per-tenant value meaningful here
instead is that the coordinating webhook route (`webhooks.py`, owned by a
different task in this wave) checks an inbound `hub.verify_token` against
*every* connected Facebook instance's own stored token, falling back to
the global `FACEBOOK_WEBHOOK_VERIFY_TOKEN` default when no per-tenant
value matches - so a tenant who has registered their own separate Meta
App's webhook subscription (rare, but supported) can set their own token
and have it honored. This adapter's job is only to store/expose that
token via `CONFIG_SCHEMA` and credential storage; it is `webhooks.py`'s
job (not this module's) to actually perform that per-instance lookup at
the GET-handshake layer.

Inbound webhook signatures are verified per-tenant, same pattern as
WhatsApp/Instagram: each tenant may supply their own `app_secret` (the
Meta App their access token belongs to) at connect time, checked in
`resolve_instance_for_webhook` - see that method's docstring. A
deployment can still set one shared `FACEBOOK_WEBHOOK_APP_SECRET` as a
fallback for tenants that share one app; `verify_webhook_signature` only
re-checks that shared fallback, deferring to the per-tenant check for
everything else.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import uuid
from typing import Any, Mapping

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
    ConnectorState,
    ConnectorType,
    HealthStatus,
)

logger = logging.getLogger(__name__)
settings = get_connector_settings()

CONNECTOR_TYPE_KEY = "facebook"

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["page_id", "page_access_token"],
    "properties": {
        "page_id": {
            "type": "string",
            "description": "Your Facebook Page's ID, from your Meta Business Suite.",
        },
        "page_access_token": {
            "type": "string",
            "description": (
                "A Page access token with `pages_messaging` permission, generated in your own Meta "
                "Business Suite."
            ),
        },
        "app_secret": {
            "type": "string",
            "description": (
                "Optional; your Meta App's secret, used to verify inbound webhook signatures for "
                "this specific instance."
            ),
        },
        "webhook_verify_token": {
            "type": "string",
            "description": (
                "Optional; a verify token for the GET webhook handshake, if you're using your own "
                "separate Meta App's webhook subscription instead of the platform default."
            ),
        },
    },
}

# Errors that mean "could not reach Meta at all" (this sandbox), as opposed
# to "reached Meta and it rejected the credentials" - only the former falls
# back to a stub result. Same set `whatsapp/adapter.py`/`instagram/adapter.py` use.
_NETWORK_UNREACHABLE_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.TimeoutException)


class FacebookAdapter(base.ConnectorAdapter):
    connector_type_key = CONNECTOR_TYPE_KEY
    auth_mode = "api_key"
    config_schema = CONFIG_SCHEMA

    async def _validate_credentials(
        self, *, page_access_token: str, page_id: str
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Returns `(is_stub, detail, connected_identity)`. Raises
        `ValueError` on a real auth/permission rejection - mirrors
        `instagram/adapter.py::_validate_credentials`.
        """
        try:
            # TODO(meta-graph-api): GET /{page_id}?fields=name&access_token={page_access_token}
            async with httpx.AsyncClient(base_url=settings.FACEBOOK_GRAPH_API_BASE_URL, timeout=10.0) as client:
                response = await client.get(
                    f"/{page_id}",
                    params={
                        "fields": "name",
                        "access_token": page_access_token,
                    },
                )
            if response.status_code in (401, 403):
                raise ValueError("Meta rejected this page_access_token/page_id pair")
            response.raise_for_status()
            data = response.json()
            return False, None, {
                "name": data.get("name"),
            }
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[facebook] could not reach %s (%s) - stub mode: assuming the credentials are valid "
                "so the connect lifecycle stays testable offline.",
                settings.FACEBOOK_GRAPH_API_BASE_URL,
                exc,
            )
            return True, str(exc), {
                "name": "fusion-flow Dev Sandbox Page (offline validation)",
            }

    async def initiate_connect(
        self,
        *,
        tenant_id: uuid.UUID,
        instance: ConnectorInstance,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> base.ConnectResult:
        page_id = params.get("page_id")
        page_access_token = params.get("page_access_token")
        app_secret = params.get("app_secret")
        webhook_verify_token = params.get("webhook_verify_token")
        if not page_id or not page_access_token:
            raise ValueError("page_id and page_access_token are required")

        is_stub, detail, identity = await self._validate_credentials(
            page_access_token=page_access_token, page_id=page_id
        )

        await connector_service.upsert_credential(
            session,
            instance=instance,
            secret={
                "page_access_token": page_access_token,
                "app_secret": app_secret or "",
                "webhook_verify_token": webhook_verify_token or "",
            },
        )

        return base.ConnectResult(
            state=ConnectorState.CONNECTED,
            connected_identity={"name": identity.get("name")},
            provider_ref_ids={"page_id": page_id},
            health_status=HealthStatus.HEALTHY,
            error_message=f"stub validation ({detail})" if is_stub else None,
        )

    async def test_connection(self, *, instance: ConnectorInstance, session: AsyncSession) -> base.HealthResult:
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail="No credential stored")

        page_id = (instance.provider_ref_ids or {}).get("page_id")
        try:
            is_stub, detail, _identity = await self._validate_credentials(
                page_access_token=secret["page_access_token"], page_id=page_id
            )
        except ValueError as exc:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail=str(exc))
        if is_stub:
            return base.HealthResult(health_status=HealthStatus.HEALTHY, detail=f"stub: assumed healthy ({detail})")
        return base.HealthResult(health_status=HealthStatus.HEALTHY)

    async def disconnect(self, *, instance: ConnectorInstance, session: AsyncSession) -> None:
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return
        page_id = (instance.provider_ref_ids or {}).get("page_id")
        # TODO(meta-graph-api): DELETE /{page_id}/subscribed_apps - revoke
        # our app's webhook subscription for this page. Best-effort: a
        # token already revoked by the user, or this sandbox having no
        # network, both surface as an `httpx.HTTPError` subclass and are
        # equally fine to just log and move on from.
        async with httpx.AsyncClient(base_url=settings.FACEBOOK_GRAPH_API_BASE_URL, timeout=10.0) as client:
            try:
                await client.delete(
                    f"/{page_id}/subscribed_apps", params={"access_token": secret["page_access_token"]}
                )
            except httpx.HTTPError as exc:
                logger.warning("[facebook] best-effort unsubscribe failed: %s", exc)

    async def send_message(
        self, *, instance: ConnectorInstance, session: AsyncSession, recipient_id: str, text: str
    ) -> None:
        """Send an outbound Facebook Page Messenger message.

        Called by the `facebook.send_message` workflow node/action.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        page_id = (instance.provider_ref_ids or {}).get("page_id")
        if not page_id:
            raise RuntimeError(f"connector instance {instance.id} has no page_id on record")

        # TODO(meta-graph-api): POST /{page_id}/messages
        #   Authorization: Bearer {page_access_token}
        #   {"recipient": {"id": "{recipient_id}"}, "message": {"text": "{text}"},
        #    "messaging_type": "RESPONSE"}
        try:
            async with httpx.AsyncClient(base_url=settings.FACEBOOK_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    f"/{page_id}/messages",
                    headers={"Authorization": f"Bearer {secret['page_access_token']}"},
                    json={
                        "recipient": {"id": recipient_id},
                        "message": {"text": text},
                        "messaging_type": "RESPONSE",
                    },
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[facebook] could not reach %s (%s) - stub mode: skipping this send so the "
                "workflow action stays testable offline (instance=%s, recipient_id=%s).",
                settings.FACEBOOK_GRAPH_API_BASE_URL,
                exc,
                instance.id,
                recipient_id,
            )

    async def perform_action(
        self, *, action: str, params: dict[str, Any], instance: ConnectorInstance, session: AsyncSession
    ) -> dict[str, Any]:
        """Dispatch for the generic `connector.action` workflow node type -
        mirrors `instagram/adapter.py::perform_action`'s style exactly."""
        if action == "send_message":
            recipient_id = params.get("recipient_id")
            text = params.get("text")
            if not recipient_id or not text:
                raise ValueError("send_message requires non-empty 'recipient_id' and 'text' params")
            await self.send_message(instance=instance, session=session, recipient_id=recipient_id, text=text)
            return {"recipient_id": recipient_id, "text": text}
        raise NotImplementedError(f"{self.connector_type_key} does not support action {action!r}")

    def webhook_setup_hint(self) -> dict[str, str] | None:
        """The Callback URL + (default) Verify Token a tenant needs to paste
        into their own Meta App's Webhooks configuration to finish wiring up
        inbound messages - shown in the UI right after connecting. This
        shows the platform DEFAULT verify token as a hint only; a tenant
        may instead set their own `webhook_verify_token` at connect time if
        they've registered their OWN separate Meta App's webhook
        subscription (rare, but the schema supports it) - see
        `resolve_instance_for_webhook`'s docstring for how a per-tenant
        token is actually honored at the GET-handshake layer, which is not
        this method's job to implement."""
        base_url = settings.BACKEND_PUBLIC_BASE_URL.rstrip("/")
        return {
            "callback_url": f"{base_url}/api/v1/webhooks/facebook",
            "verify_token": settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN,
        }

    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
        """Generic-layer check against a global fallback secret only - mirrors
        `instagram/adapter.py`'s identical rationale: each tenant's own
        `app_secret` is checked inside `resolve_instance_for_webhook` (it has
        to know *which* instance's secret to check before it can verify
        anything); this method only matters for a deployment that sets one
        shared `FACEBOOK_WEBHOOK_APP_SECRET` for every tenant - when unset,
        this defers entirely to the per-instance check and returns True."""
        app_secret = settings.FACEBOOK_WEBHOOK_APP_SECRET
        if not app_secret:
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
        """Match the inbound Facebook Page id (`entry[0].id`) against a
        stored instance, then verify the signature against **that
        instance's own** stored `app_secret` - each tenant brings their own
        Facebook Page credentials (see module docstring), so their webhook
        deliveries are signed with their own Meta App's secret, not a
        shared platform one. Falls back to the global
        `FACEBOOK_WEBHOOK_APP_SECRET` only for a tenant that didn't supply
        their own - mirrors `instagram/adapter.py`'s identical
        per-instance-then-global pattern. If neither is configured, the
        webhook is accepted unverified (dev-only fallback).

        Cross-tenant lookup by necessity: a Meta webhook carries no tenant/JWT,
        only the Facebook Page id, and no `SET LOCAL app.current_tenant_id`
        has run on this connection. In production this lookup must run through
        a DB role granted `BYPASSRLS` scoped only to webhook ingestion
        (mirroring `require_platform_admin`'s separate admin-only role) - that
        second role is not provisioned in this dev environment; see this
        task's final report.
        """
        try:
            body = json.loads(raw_payload)
        except json.JSONDecodeError:
            return None
        entries = body.get("entry") or []
        if not entries:
            return None
        page_id = entries[0].get("id")
        if not page_id:
            return None

        rows = await session.execute(
            select(ConnectorInstance)
            .join(ConnectorType, ConnectorType.id == ConnectorInstance.connector_type_id)
            .where(
                ConnectorType.key == CONNECTOR_TYPE_KEY,
                ConnectorInstance.provider_ref_ids["page_id"].astext == page_id,
            )
        )
        instance = rows.scalars().first()
        if instance is None:
            return None

        secret = await connector_service.get_credential_secret(session, instance=instance)
        app_secret = (secret or {}).get("app_secret") or settings.FACEBOOK_WEBHOOK_APP_SECRET
        if not app_secret:
            logger.warning(
                "[facebook] no per-tenant or global webhook app secret configured for instance=%s - "
                "accepting webhook unverified (dev only)",
                instance.id,
            )
            return instance

        signature_header = headers.get("x-hub-signature-256", "")
        if not signature_header.startswith("sha256="):
            return None
        expected = hmac.new(app_secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        provided = signature_header[len("sha256=") :]
        if not hmac.compare_digest(expected, provided):
            return None
        return instance

    @staticmethod
    def _extract_inbound_message(body: dict[str, Any]) -> dict[str, Any] | None:
        """Pull the first inbound message out of a Facebook Page Messenger
        webhook body. Real shape (Meta docs):
          entry[0].messaging[0] = {"sender": {"id": "<psid>"},
            "recipient": {"id": "<page_id>"}, "timestamp": ...,
            "message": {"mid": "...", "text": "..."}}
        Same shape Instagram's own Messaging webhook uses - adapted from
        `instagram/adapter.py::_extract_inbound_message`.
        """
        entries = body.get("entry") or []
        for entry in entries:
            for messaging in entry.get("messaging") or []:
                message = messaging.get("message")
                if not message:
                    continue
                return {
                    "from": (messaging.get("sender") or {}).get("id"),
                    "message_id": message.get("mid"),
                    "text": message.get("text"),
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

        # Deferred import: `modules.workflows` (package __init__) imports
        # its built-in nodes, one of which may import *this* module for the
        # `adapter` singleton - importing `event_bus` at module level here
        # would be a circular import. Same convention as
        # `instagram/adapter.py::handle_webhook`/`whatsapp/adapter.py`.
        from fusionflow.modules.workflows.engine import event_bus

        # Deferred import: same circular-import dodge as `event_bus` above.
        from fusionflow.modules.inbox import service as inbox_service

        inbound_message = self._extract_inbound_message(body)
        if inbound_message is not None:
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="facebook.message_received",
                payload={
                    "from": inbound_message.get("from"),
                    "message_id": inbound_message.get("message_id"),
                    "text": inbound_message.get("text"),
                },
                connector_instance_id=instance.id,
                dedupe_key=inbound_message.get("message_id"),
            )
            # Unified Inbox: same shape as Instagram's DM branch.
            if inbound_message.get("text"):
                await inbox_service.upsert_inbound_message(
                    session,
                    instance=instance,
                    external_contact_id=inbound_message.get("from"),
                    content=inbound_message.get("text"),
                    external_message_id=inbound_message.get("message_id"),
                    display_name=None,
                )

        # Facebook Pages don't have an Instagram-style "comment" webhook
        # field in this same shape - messages only, no comment handling.

        return [event]


adapter = FacebookAdapter()
base.registry.register(adapter)
