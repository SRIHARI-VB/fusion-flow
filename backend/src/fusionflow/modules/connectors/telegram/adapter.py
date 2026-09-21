"""Telegram connector adapter (Telegram Bot API).

`auth_mode="api_key"`: each tenant brings their own bot, created via
@BotFather in their own Telegram account - no platform-level Telegram
app/credentials exist or are needed, the same BYO-credentials model
`razorpay/adapter.py`/`whatsapp/adapter.py` already established for this
codebase. Three things make Telegram's shape genuinely different from
every other adapter here:

1. **Bot token lives in the URL path, not a header/query param.** Every
   Telegram Bot API call is `https://api.telegram.org/bot{token}/{method}`
   - there is no `Authorization` header or `access_token`/`key_secret`
   query param to attach separately. `_api_url` is the one place that
   builds this per-instance URL from the stored token; nothing here uses a
   fixed `httpx.AsyncClient(base_url=...)` the way WhatsApp/Razorpay do,
   since the "base" itself changes per call.

2. **The webhook is self-registered, not manually pasted.** Meta-based
   connectors (WhatsApp/Instagram/Facebook) hand the tenant a fixed
   `callback_url` + `verify_token` (`webhook_setup_hint`) for them to paste
   into their own dashboard, because Meta's webhook payload carries a
   tenant-identifying id (a WABA/page/IG-account id) that a shared callback
   URL can dispatch on. Telegram's `setWebhook` API call instead lets *us*
   choose the callback URL per bot - so `initiate_connect` registers
   `{BACKEND_PUBLIC_BASE_URL}/api/v1/webhooks/telegram?instance_id={instance.id}`
   at connect time, and `resolve_instance_for_webhook` reads
   `?instance_id=` straight off the query string to resolve the instance -
   no payload inspection, no brute-force-over-all-instances fallback (unlike
   `razorpay/adapter.py`, where the same query param is only a *fallback*
   for a manually-pasted URL, here it's the sole and always-present
   mechanism since we control registration). Because there is nothing left
   for a human to paste into a dashboard, `webhook_setup_hint` returns
   `None`.

3. **Authenticity is a plain secret-token header, not an HMAC signature.**
   `setWebhook` accepts a `secret_token` we choose; Telegram echoes it back
   verbatim as the `X-Telegram-Bot-Api-Secret-Token` header on every
   delivery. There is no signing/hashing involved - verification is a
   direct `hmac.compare_digest` string comparison against the token stored
   for that instance (falling back to the deployment-wide
   `TELEGRAM_WEBHOOK_SECRET_TOKEN`), the same per-instance-then-global
   fallback shape `whatsapp/adapter.py`'s `app_secret` check uses, just
   without any hashing step.

Every outbound call that cannot even reach the network (this sandbox has
none) is caught narrowly (`_NETWORK_UNREACHABLE_ERRORS`) and downgraded to
a clearly-logged stub result so the connect/send/disconnect lifecycle
stays testable - an actual rejection from Telegram (bad token, bad chat
id, ...) is a real error and is never swallowed, same convention as every
other adapter in this package. The one exception is the best-effort
`setWebhook` call inside `initiate_connect`: since the bot token itself
already validated via `getMe` by that point, a failure to register the
webhook (network-unreachable OR a real rejection from Telegram) is only
logged, never raised - mirroring `whatsapp/adapter.py::disconnect`'s
"best-effort provider-side call" tone rather than the stricter
credential-validation tone `_validate_bot_token` uses.
"""

from __future__ import annotations

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

CONNECTOR_TYPE_KEY = "telegram"

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["bot_token"],
    "properties": {
        "bot_token": {
            "type": "string",
            "description": "The bot token from @BotFather (Telegram > search @BotFather > /newbot).",
        },
        "webhook_secret_token": {
            "type": "string",
            "description": (
                "Optional; a token of your choosing, verified against Telegram's "
                "`X-Telegram-Bot-Api-Secret-Token` header on inbound webhooks. Leave blank to use "
                "the platform default."
            ),
        },
    },
}

# Errors that mean "could not reach Telegram at all" (this sandbox), as
# opposed to "reached Telegram and it rejected the request" - only the
# former falls back to a stub result. Same set every other adapter in this
# package uses.
_NETWORK_UNREACHABLE_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.TimeoutException)


def _api_url(bot_token: str, method: str) -> str:
    """Telegram's bot-token-in-path URL shape - see module docstring point 1."""
    return f"{settings.TELEGRAM_BOT_API_BASE_URL}/bot{bot_token}/{method}"


class TelegramAdapter(base.ConnectorAdapter):
    connector_type_key = CONNECTOR_TYPE_KEY
    auth_mode = "api_key"
    config_schema = CONFIG_SCHEMA

    async def _validate_bot_token(self, *, bot_token: str) -> tuple[bool, str | None, dict[str, Any]]:
        """Returns `(is_stub, detail, identity)` where `identity` is
        Telegram's `getMe` result (`id`/`username`/`first_name`). Raises
        `ValueError` on a real rejection - Telegram responds `{"ok": false,
        "description": "..."}` with a 401 status for a bad token; mirrors
        `whatsapp/adapter.py::_validate_credentials`'s exact
        narrow-rejection-vs-network-unreachable split.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(_api_url(bot_token, "getMe"))
            data = response.json()
            if response.status_code == 401 or not data.get("ok"):
                raise ValueError(data.get("description") or "Telegram rejected this bot token")
            response.raise_for_status()
            result = data.get("result") or {}
            return False, None, {
                "id": result.get("id"),
                "username": result.get("username"),
                "first_name": result.get("first_name"),
            }
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[telegram] could not reach %s (%s) - stub mode: assuming the bot token is valid so "
                "the connect lifecycle stays testable offline.",
                settings.TELEGRAM_BOT_API_BASE_URL,
                exc,
            )
            return True, str(exc), {
                "id": 0,
                "username": "dev_sandbox_bot",
                "first_name": "fusion-flow Dev Sandbox",
            }

    async def initiate_connect(
        self,
        *,
        tenant_id: uuid.UUID,
        instance: ConnectorInstance,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> base.ConnectResult:
        bot_token = params.get("bot_token")
        webhook_secret_token = params.get("webhook_secret_token")
        if not bot_token:
            raise ValueError("bot_token is required")

        is_stub, detail, identity = await self._validate_bot_token(bot_token=bot_token)
        bot_id = identity.get("id")

        # Self-register the webhook (module docstring point 2). Best-effort:
        # the bot token itself already validated above, so a failure here
        # (network-unreachable or a real rejection from Telegram) is only
        # logged, never raised - mirrors
        # `whatsapp/adapter.py::disconnect`'s best-effort provider-side-call
        # tone, not `_validate_bot_token`'s stricter validation tone.
        webhook_url = (
            f"{settings.BACKEND_PUBLIC_BASE_URL.rstrip('/')}/api/v1/webhooks/telegram"
            f"?instance_id={instance.id}"
        )
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    _api_url(bot_token, "setWebhook"),
                    json={
                        "url": webhook_url,
                        "secret_token": webhook_secret_token or settings.TELEGRAM_WEBHOOK_SECRET_TOKEN or "",
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning(
                "[telegram] best-effort setWebhook registration failed (%s) - continuing connect "
                "since the bot token itself already validated fine (instance=%s, url=%s).",
                exc,
                instance.id,
                webhook_url,
            )

        await connector_service.upsert_credential(
            session,
            instance=instance,
            secret={"bot_token": bot_token, "webhook_secret_token": webhook_secret_token or ""},
        )

        return base.ConnectResult(
            state=ConnectorState.CONNECTED,
            connected_identity={"username": identity.get("username"), "first_name": identity.get("first_name")},
            provider_ref_ids={"bot_id": str(bot_id)},
            health_status=HealthStatus.HEALTHY,
            error_message=f"stub validation ({detail})" if is_stub else None,
        )

    async def test_connection(self, *, instance: ConnectorInstance, session: AsyncSession) -> base.HealthResult:
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail="No credential stored")
        try:
            is_stub, detail, _identity = await self._validate_bot_token(bot_token=secret["bot_token"])
        except ValueError as exc:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail=str(exc))
        if is_stub:
            return base.HealthResult(health_status=HealthStatus.HEALTHY, detail=f"stub: assumed healthy ({detail})")
        return base.HealthResult(health_status=HealthStatus.HEALTHY)

    async def disconnect(self, *, instance: ConnectorInstance, session: AsyncSession) -> None:
        """Best-effort `deleteWebhook` - nothing else to revoke for a bot
        token a tenant generated themselves via @BotFather. Mirrors
        `cloudflare_r2/adapter.py::disconnect`'s tone: a narrow
        `httpx.HTTPError` catch that only logs, never raises.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(_api_url(secret["bot_token"], "deleteWebhook"))
        except httpx.HTTPError as exc:
            logger.warning("[telegram] best-effort deleteWebhook failed: %s", exc)

    async def send_message(
        self, *, instance: ConnectorInstance, session: AsyncSession, chat_id: Any, text: str
    ) -> None:
        """Send an outbound text message via `sendMessage`. Called by the
        generic `connector.action` node type through `perform_action`
        below."""
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(
                    _api_url(secret["bot_token"], "sendMessage"),
                    json={"chat_id": chat_id, "text": text},
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[telegram] could not reach %s (%s) - stub mode: skipping this send so the workflow "
                "action stays testable offline (instance=%s, chat_id=%s).",
                settings.TELEGRAM_BOT_API_BASE_URL,
                exc,
                instance.id,
                chat_id,
            )

    async def perform_action(
        self, *, action: str, params: dict[str, Any], instance: ConnectorInstance, session: AsyncSession
    ) -> dict[str, Any]:
        """Dispatch for the generic `connector.action` workflow node type
        (see `base.ConnectorAdapter.perform_action`'s docstring) - mirrors
        `whatsapp/adapter.py::perform_action`'s style exactly."""
        if action == "send_message":
            chat_id = params.get("chat_id")
            text = params.get("text")
            if not chat_id or not text:
                raise ValueError("send_message requires non-empty 'chat_id' and 'text' params")
            await self.send_message(instance=instance, session=session, chat_id=chat_id, text=text)
            return {"chat_id": chat_id, "text": text}
        raise NotImplementedError(f"{self.connector_type_key} does not support action {action!r}")

    def webhook_setup_hint(self) -> dict[str, str] | None:
        """Unlike WhatsApp/Instagram/Facebook (which need a human to paste a
        callback URL into Meta's dashboard), Telegram's webhook is fully
        self-registered via the `setWebhook` call in `initiate_connect` -
        there is nothing for the UI to show the tenant."""
        return None

    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
        """Generic-layer check against the global fallback secret token
        only - mirrors `whatsapp/adapter.py`'s identical rationale: each
        instance's own `webhook_secret_token` is checked inside
        `resolve_instance_for_webhook` (it has to know *which* instance's
        token to check before it can verify anything); this method only
        matters for a deployment that sets one shared
        `TELEGRAM_WEBHOOK_SECRET_TOKEN` for every tenant - when unset, this
        defers entirely to the per-instance check and returns True."""
        secret_token = settings.TELEGRAM_WEBHOOK_SECRET_TOKEN
        if not secret_token:
            return True
        provided = headers.get("x-telegram-bot-api-secret-token", "")
        return hmac.compare_digest(secret_token, provided)

    async def resolve_instance_for_webhook(
        self,
        *,
        raw_payload: bytes,
        headers: Mapping[str, str],
        query_params: Mapping[str, str],
        session: AsyncSession,
    ) -> ConnectorInstance | None:
        """Identify the instance from `?instance_id=` on the URL - the
        **primary and only** resolution mechanism here (not a fallback, as
        it is in `razorpay/adapter.py`): a standard Telegram webhook payload
        carries no bot/tenant identifier at all (unlike WhatsApp/Instagram,
        where Meta puts an account id in the payload), so there is nothing
        to brute-force or match against. This works because *we* choose the
        callback URL when registering it via `setWebhook` in
        `initiate_connect` - its absence on an inbound request means
        misconfiguration, not a legitimate case to fall back from.

        Once the instance is identified, its own stored
        `webhook_secret_token` (falling back to the global
        `TELEGRAM_WEBHOOK_SECRET_TOKEN`) is checked against the
        `X-Telegram-Bot-Api-Secret-Token` header - this doubles as the
        authoritative signature-equivalent check, see
        `verify_webhook_signature`. If neither is configured, the webhook is
        accepted unverified (dev-only fallback, mirrors
        `whatsapp/adapter.py`'s identical convention).

        Cross-tenant lookup by necessity: this runs before any tenant
        context exists on `session` - see `base.ConnectorAdapter
        .resolve_instance_for_webhook`'s docstring and webhooks.py's module
        docstring for the RLS implication.
        """
        instance_id_param = query_params.get("instance_id")
        if not instance_id_param:
            return None
        try:
            instance_id = uuid.UUID(instance_id_param)
        except ValueError:
            return None

        rows = await session.execute(
            select(ConnectorInstance)
            .join(ConnectorType, ConnectorType.id == ConnectorInstance.connector_type_id)
            .where(ConnectorType.key == CONNECTOR_TYPE_KEY, ConnectorInstance.id == instance_id)
        )
        instance = rows.scalars().first()
        if instance is None:
            return None

        secret = await connector_service.get_credential_secret(session, instance=instance)
        expected_secret_token = (secret or {}).get("webhook_secret_token") or settings.TELEGRAM_WEBHOOK_SECRET_TOKEN
        if not expected_secret_token:
            logger.warning(
                "[telegram] no per-instance or global webhook secret token configured for "
                "instance=%s - accepting webhook unverified (dev only)",
                instance.id,
            )
            return instance

        provided = headers.get("x-telegram-bot-api-secret-token", "")
        if not hmac.compare_digest(expected_secret_token, provided):
            return None
        return instance

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

        # Deferred import: same circular-import dodge as
        # `whatsapp/adapter.py::handle_webhook` (`modules.workflows`'s
        # __init__ imports built-in nodes, one of which imports this module
        # for the `adapter` singleton).
        from fusionflow.modules.workflows.engine import event_bus

        # Deferred import: same circular-import dodge as `event_bus` above.
        from fusionflow.modules.inbox import service as inbox_service

        # Telegram sends `edited_message` under the same shape as `message`
        # when a user edits a previous message - preferring `message` when
        # both are somehow present (they never are in practice).
        message = body.get("message") or body.get("edited_message")
        if message and message.get("text"):
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="telegram.message_received",
                payload={
                    "chat_id": (message.get("chat") or {}).get("id"),
                    "message_id": message.get("message_id"),
                    "text": message.get("text"),
                    "from_username": (message.get("from") or {}).get("username"),
                },
                connector_instance_id=instance.id,
                dedupe_key=str(message.get("message_id")),
            )
            # Unified Inbox: chat id cast to str - `external_contact_id` is
            # a string column, Telegram chat ids are integers.
            await inbox_service.upsert_inbound_message(
                session,
                instance=instance,
                external_contact_id=str((message.get("chat") or {}).get("id")),
                content=message.get("text"),
                external_message_id=str(message.get("message_id")),
                display_name=(message.get("from") or {}).get("username"),
            )

        return [event]


adapter = TelegramAdapter()
base.registry.register(adapter)
