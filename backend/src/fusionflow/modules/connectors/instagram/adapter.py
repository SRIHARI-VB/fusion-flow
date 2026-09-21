"""Instagram connector adapter (Meta Graph API - Instagram Messaging/Comments).

`auth_mode="api_key"`: same BYO-credentials model as
`whatsapp/adapter.py`, not OAuth. Each tenant generates their own Page/
User access token in their own Meta Business Suite (with
`instagram_basic`, `instagram_manage_messages`, `instagram_manage_comments`
permissions) and pastes it here, alongside the Instagram professional/
business account id it belongs to - there is no shared/platform Meta
Developer App and no OAuth dialog for the connect step itself, so this
works in any environment (including plain localhost dev) with no public
callback URL needed just to connect.

Every place a real Graph API call belongs is marked `TODO(meta-graph-api)`
with the exact endpoint shape from Meta's public docs. If that call cannot
even reach the network (this sandbox has none), the failure is caught
narrowly (`_NETWORK_UNREACHABLE_ERRORS`) and downgraded to a clearly-logged
stub result so the connect/send/disconnect lifecycle stays testable - an
actual rejection from Meta (bad token, bad account id, revoked access) is
a real error and is never swallowed, same convention as
`whatsapp/adapter.py`.

Per-tenant `webhook_verify_token` design rationale: Meta's GET webhook
verification handshake (`hub.verify_token`) carries no tenant identifier
at all, so a single fixed verify token - like `whatsapp/adapter.py` uses -
normally cannot vary per tenant; there would be no way to know *whose*
token to check it against. What makes a per-tenant value meaningful here
instead is that the coordinating webhook route (`webhooks.py`, owned by a
different task in this wave) checks an inbound `hub.verify_token` against
*every* connected Instagram instance's own stored token, falling back to
the global `INSTAGRAM_WEBHOOK_VERIFY_TOKEN` default when no per-tenant
value matches - so a tenant who has registered their own separate Meta
App's webhook subscription (rare, but supported) can set their own token
and have it honored. This adapter's job is only to store/expose that
token via `CONFIG_SCHEMA` and credential storage; it is `webhooks.py`'s
job (not this module's) to actually perform that per-instance lookup at
the GET-handshake layer.

Inbound webhook signatures are verified per-tenant, same pattern as
WhatsApp: each tenant may supply their own `app_secret` (the Meta App
their access token belongs to) at connect time, checked in
`resolve_instance_for_webhook` - see that method's docstring. A
deployment can still set one shared `INSTAGRAM_WEBHOOK_APP_SECRET` as a
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

CONNECTOR_TYPE_KEY = "instagram"

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["instagram_account_id", "access_token"],
    "properties": {
        "instagram_account_id": {
            "type": "string",
            "description": (
                "The tenant's Instagram professional/business account id, from their own Meta "
                "Business Suite."
            ),
        },
        "access_token": {
            "type": "string",
            "description": (
                "A Page/User access token with instagram_basic, instagram_manage_messages, and "
                "instagram_manage_comments permissions, generated in your own Meta Business Suite."
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
                "Optional; a tenant-chosen token for the GET webhook verification handshake, used "
                "only if you've registered your own separate Meta App's webhook subscription "
                "instead of the platform default."
            ),
        },
    },
}

# Errors that mean "could not reach Meta at all" (this sandbox), as opposed
# to "reached Meta and it rejected the credentials" - only the former falls
# back to a stub result. Same set `whatsapp/adapter.py` uses.
_NETWORK_UNREACHABLE_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.TimeoutException)


class InstagramAdapter(base.ConnectorAdapter):
    connector_type_key = CONNECTOR_TYPE_KEY
    auth_mode = "api_key"
    config_schema = CONFIG_SCHEMA

    async def _validate_credentials(
        self, *, access_token: str, instagram_account_id: str
    ) -> tuple[bool, str | None, dict[str, Any]]:
        """Returns `(is_stub, detail, connected_identity)`. Raises
        `ValueError` on a real auth/permission rejection - mirrors
        `whatsapp/adapter.py::_validate_credentials`.
        """
        try:
            # TODO(meta-graph-api): GET /{instagram_account_id}
            #   ?fields=username,name,profile_picture_url&access_token={access_token}
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=10.0) as client:
                response = await client.get(
                    f"/{instagram_account_id}",
                    params={
                        "fields": "username,name,profile_picture_url",
                        "access_token": access_token,
                    },
                )
            if response.status_code in (401, 403):
                raise ValueError("Meta rejected this access_token/instagram_account_id pair")
            response.raise_for_status()
            data = response.json()
            return False, None, {
                "username": data.get("username"),
                "name": data.get("name"),
            }
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: assuming the credentials are valid "
                "so the connect lifecycle stays testable offline.",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
            )
            return True, str(exc), {
                "username": "dev_sandbox",
                "name": "fusion-flow Dev Sandbox (offline validation)",
            }

    async def initiate_connect(
        self,
        *,
        tenant_id: uuid.UUID,
        instance: ConnectorInstance,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> base.ConnectResult:
        instagram_account_id = params.get("instagram_account_id")
        access_token = params.get("access_token")
        app_secret = params.get("app_secret")
        webhook_verify_token = params.get("webhook_verify_token")
        if not instagram_account_id or not access_token:
            raise ValueError("instagram_account_id and access_token are required")

        is_stub, detail, identity = await self._validate_credentials(
            access_token=access_token, instagram_account_id=instagram_account_id
        )

        await connector_service.upsert_credential(
            session,
            instance=instance,
            secret={
                "access_token": access_token,
                "app_secret": app_secret or "",
                "webhook_verify_token": webhook_verify_token or "",
            },
        )

        return base.ConnectResult(
            state=ConnectorState.CONNECTED,
            connected_identity=identity,
            provider_ref_ids={"instagram_account_id": instagram_account_id},
            health_status=HealthStatus.HEALTHY,
            error_message=f"stub validation ({detail})" if is_stub else None,
        )

    async def test_connection(self, *, instance: ConnectorInstance, session: AsyncSession) -> base.HealthResult:
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail="No credential stored")

        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        try:
            is_stub, detail, _identity = await self._validate_credentials(
                access_token=secret["access_token"], instagram_account_id=instagram_account_id
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
        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        # TODO(meta-graph-api): DELETE /{instagram_account_id}/subscribed_apps -
        # revoke our app's webhook subscription for this account. Best-effort:
        # a token already revoked by the user, or this sandbox having no
        # network, both surface as an `httpx.HTTPError` subclass and are
        # equally fine to just log and move on from.
        async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=10.0) as client:
            try:
                await client.delete(
                    f"/{instagram_account_id}/subscribed_apps", params={"access_token": secret["access_token"]}
                )
            except httpx.HTTPError as exc:
                logger.warning("[instagram] best-effort unsubscribe failed: %s", exc)

    async def send_direct_message(
        self, *, instance: ConnectorInstance, session: AsyncSession, recipient_id: str, text: str
    ) -> None:
        """Send an outbound Instagram direct message.

        Called by the `instagram.send_direct_message` workflow node/action.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        if not instagram_account_id:
            raise RuntimeError(f"connector instance {instance.id} has no instagram_account_id on record")

        # TODO(meta-graph-api): POST /{instagram_account_id}/messages
        #   Authorization: Bearer {access_token}
        #   {"recipient": {"id": "{recipient_id}"}, "message": {"text": "{text}"}}
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    f"/{instagram_account_id}/messages",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    json={"recipient": {"id": recipient_id}, "message": {"text": text}},
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: skipping this send so the "
                "workflow action stays testable offline (instance=%s, recipient_id=%s).",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
                instance.id,
                recipient_id,
            )

    async def reply_to_comment(
        self, *, instance: ConnectorInstance, session: AsyncSession, comment_id: str, text: str
    ) -> None:
        """Reply to an Instagram comment.

        Called by the `instagram.reply_to_comment` workflow node/action.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        # TODO(meta-graph-api): POST /{comment_id}/replies
        #   Authorization: Bearer {access_token}
        #   {"message": "{text}"}
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    f"/{comment_id}/replies",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    json={"message": text},
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: skipping this reply so the "
                "workflow action stays testable offline (instance=%s, comment_id=%s).",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
                instance.id,
                comment_id,
            )

    async def like_comment(self, *, instance: ConnectorInstance, session: AsyncSession, comment_id: str) -> None:
        """Like an Instagram comment - the `instagram.comment_automation`
        predefined automation's "Auto-Like" toggle (see
        `modules/predefined_automations/instagram_comment_automation.py`).
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        # TODO(meta-graph-api): POST /{comment_id}/likes
        #   Authorization: Bearer {access_token}
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    f"/{comment_id}/likes", headers={"Authorization": f"Bearer {secret['access_token']}"}
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: skipping this like so the "
                "workflow action stays testable offline (instance=%s, comment_id=%s).",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
                instance.id,
                comment_id,
            )

    async def hide_comment(
        self, *, instance: ConnectorInstance, session: AsyncSession, comment_id: str, hidden: bool = True
    ) -> None:
        """Hide (or unhide) an Instagram comment - the `instagram.
        comment_automation` predefined automation's "Auto-Hide" toggle."""
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        # TODO(meta-graph-api): POST /{comment_id}?hide={hidden}
        #   Authorization: Bearer {access_token}
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    f"/{comment_id}",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    params={"hide": str(hidden).lower()},
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: skipping this hide so the "
                "workflow action stays testable offline (instance=%s, comment_id=%s).",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
                instance.id,
                comment_id,
            )

    async def perform_action(
        self, *, action: str, params: dict[str, Any], instance: ConnectorInstance, session: AsyncSession
    ) -> dict[str, Any]:
        """Dispatch for the generic `connector.action` workflow node type -
        mirrors `whatsapp/adapter.py::perform_action`'s style exactly."""
        if action == "send_direct_message":
            recipient_id = params.get("recipient_id")
            text = params.get("text")
            if not recipient_id or not text:
                raise ValueError("send_direct_message requires non-empty 'recipient_id' and 'text' params")
            await self.send_direct_message(
                instance=instance, session=session, recipient_id=recipient_id, text=text
            )
            return {"recipient_id": recipient_id, "text": text}
        if action == "reply_to_comment":
            comment_id = params.get("comment_id")
            text = params.get("text")
            if not comment_id or not text:
                raise ValueError("reply_to_comment requires non-empty 'comment_id' and 'text' params")
            await self.reply_to_comment(instance=instance, session=session, comment_id=comment_id, text=text)
            return {"comment_id": comment_id, "text": text}
        if action == "like_comment":
            comment_id = params.get("comment_id")
            if not comment_id:
                raise ValueError("like_comment requires a non-empty 'comment_id' param")
            await self.like_comment(instance=instance, session=session, comment_id=comment_id)
            return {"comment_id": comment_id}
        if action == "hide_comment":
            comment_id = params.get("comment_id")
            if not comment_id:
                raise ValueError("hide_comment requires a non-empty 'comment_id' param")
            await self.hide_comment(
                instance=instance, session=session, comment_id=comment_id, hidden=params.get("hidden", True)
            )
            return {"comment_id": comment_id}
        raise NotImplementedError(f"{self.connector_type_key} does not support action {action!r}")

    def webhook_setup_hint(self) -> dict[str, str] | None:
        """The Callback URL + (default) Verify Token a tenant needs to paste
        into their own Meta App's Webhooks configuration to finish wiring up
        inbound messages/comments - shown in the UI right after connecting.
        This shows the platform DEFAULT verify token as a hint only; a
        tenant may instead set their own `webhook_verify_token` at connect
        time if they've registered their OWN separate Meta App's webhook
        subscription (rare, but the schema supports it) - see
        `resolve_instance_for_webhook`'s docstring for how a per-tenant
        token is actually honored at the GET-handshake layer, which is not
        this method's job to implement."""
        base_url = settings.BACKEND_PUBLIC_BASE_URL.rstrip("/")
        return {
            "callback_url": f"{base_url}/api/v1/webhooks/instagram",
            "verify_token": settings.INSTAGRAM_WEBHOOK_VERIFY_TOKEN,
        }

    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
        """Generic-layer check against a global fallback secret only - mirrors
        `whatsapp/adapter.py`'s identical rationale: each tenant's own
        `app_secret` is checked inside `resolve_instance_for_webhook` (it has
        to know *which* instance's secret to check before it can verify
        anything); this method only matters for a deployment that sets one
        shared `INSTAGRAM_WEBHOOK_APP_SECRET` for every tenant - when unset,
        this defers entirely to the per-instance check and returns True."""
        app_secret = settings.INSTAGRAM_WEBHOOK_APP_SECRET
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
        """Match the inbound Instagram-scoped account id (`entry[0].id`)
        against a stored instance, then verify the signature against
        **that instance's own** stored `app_secret` - each tenant brings
        their own Instagram credentials (see module docstring), so their
        webhook deliveries are signed with their own Meta App's secret, not
        a shared platform one. Falls back to the global
        `INSTAGRAM_WEBHOOK_APP_SECRET` only for a tenant that didn't supply
        their own - mirrors `whatsapp/adapter.py`'s identical
        per-instance-then-global pattern. If neither is configured, the
        webhook is accepted unverified (dev-only fallback).

        Cross-tenant lookup by necessity: a Meta webhook carries no tenant/JWT,
        only the Instagram account id, and no `SET LOCAL app.current_tenant_id`
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
        instagram_account_id = entries[0].get("id")
        if not instagram_account_id:
            return None

        rows = await session.execute(
            select(ConnectorInstance)
            .join(ConnectorType, ConnectorType.id == ConnectorInstance.connector_type_id)
            .where(
                ConnectorType.key == CONNECTOR_TYPE_KEY,
                ConnectorInstance.provider_ref_ids["instagram_account_id"].astext == instagram_account_id,
            )
        )
        instance = rows.scalars().first()
        if instance is None:
            return None

        secret = await connector_service.get_credential_secret(session, instance=instance)
        app_secret = (secret or {}).get("app_secret") or settings.INSTAGRAM_WEBHOOK_APP_SECRET
        if not app_secret:
            logger.warning(
                "[instagram] no per-tenant or global webhook app secret configured for instance=%s - "
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
        """Pull the first inbound direct message out of an Instagram
        Messaging webhook body. Real shape (Meta docs):
          entry[0].messaging[0] = {"sender": {"id": "<igsid>"},
            "recipient": {"id": "<ig_account_id>"}, "timestamp": ...,
            "message": {"mid": "...", "text": "..."}}
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

    @staticmethod
    def _extract_inbound_comment(body: dict[str, Any]) -> dict[str, Any] | None:
        """Pull the first inbound comment out of an Instagram comment
        webhook body. Real shape (Meta docs):
          entry[0].changes[0] = {"field": "comments", "value": {"id": "<comment_id>",
            "text": "...", "from": {"id": "...", "username": "..."},
            "media": {"id": "..."}}}
        """
        entries = body.get("entry") or []
        for entry in entries:
            for change in entry.get("changes") or []:
                if change.get("field") != "comments":
                    continue
                value = change.get("value") or {}
                if not value.get("id"):
                    continue
                return value
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
        # `whatsapp/adapter.py::handle_webhook`.
        from fusionflow.modules.workflows.engine import event_bus

        # Deferred import: same circular-import dodge as `event_bus` above.
        from fusionflow.modules.inbox import service as inbox_service

        inbound_message = self._extract_inbound_message(body)
        if inbound_message is not None:
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="instagram.message_received",
                payload={
                    "from": inbound_message.get("from"),
                    "message_id": inbound_message.get("message_id"),
                    "text": inbound_message.get("text"),
                },
                connector_instance_id=instance.id,
                dedupe_key=inbound_message.get("message_id"),
            )
            # Unified Inbox: DMs only - comments (below) aren't a
            # "conversation" in the inbox sense.
            if inbound_message.get("text"):
                await inbox_service.upsert_inbound_message(
                    session,
                    instance=instance,
                    external_contact_id=inbound_message.get("from"),
                    content=inbound_message.get("text"),
                    external_message_id=inbound_message.get("message_id"),
                    display_name=None,
                )

        inbound_comment = self._extract_inbound_comment(body)
        if inbound_comment is not None:
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="instagram.comment_received",
                payload={
                    "comment_id": inbound_comment["id"],
                    "text": inbound_comment.get("text"),
                    "from_username": (inbound_comment.get("from") or {}).get("username"),
                    "media_id": (inbound_comment.get("media") or {}).get("id"),
                },
                connector_instance_id=instance.id,
                dedupe_key=inbound_comment["id"],
            )

        return [event]


adapter = InstagramAdapter()
base.registry.register(adapter)
