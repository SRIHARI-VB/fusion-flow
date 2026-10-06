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
                "An Instagram access token (from Instagram API with Instagram Login - starts with "
                "'IGA') with instagram_business_basic, instagram_business_manage_messages, and "
                "instagram_business_manage_comments permissions, generated in your own Meta "
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
        except httpx.HTTPStatusError as exc:
            # A real Meta rejection (bad token, closed 24h messaging window,
            # rate limit, ...) must not be swallowed like the network-
            # unreachable case above - re-raise with Meta's own error
            # message so the caller gets a diagnosable failure instead of a
            # raw exception, same convention as `set_ice_breakers`.
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise ValueError(f"Meta rejected the direct message send: {detail}") from exc

    async def send_media_message(
        self,
        *,
        instance: ConnectorInstance,
        session: AsyncSession,
        recipient_id: str,
        media_url: str,
        media_type: str = "image",
    ) -> None:
        """Send an outbound Instagram DM carrying an image or video
        attachment instead of (or alongside a caption baked into) plain
        text - the media-attachment option on DM/story-reply/button-menu
        automations. `media_url` is a real, publicly-fetchable URL (this
        codebase's Cloudflare R2 upload path, or any already-catalogued
        Media Library asset - see `MediaPicker.tsx`); Meta fetches and
        re-hosts it server-side rather than accepting a raw file upload
        here.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        if not instagram_account_id:
            raise RuntimeError(f"connector instance {instance.id} has no instagram_account_id on record")

        # TODO(meta-graph-api): POST /{instagram_account_id}/messages
        #   Authorization: Bearer {access_token}
        #   {"recipient": {"id": "{recipient_id}"}, "message": {"attachment":
        #     {"type": "{media_type}", "payload": {"url": "{media_url}"}}}}
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=20.0) as client:
                response = await client.post(
                    f"/{instagram_account_id}/messages",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    json={
                        "recipient": {"id": recipient_id},
                        "message": {"attachment": {"type": media_type, "payload": {"url": media_url}}},
                    },
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: skipping this media send so "
                "the workflow action stays testable offline (instance=%s, recipient_id=%s).",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
                instance.id,
                recipient_id,
            )
        except httpx.HTTPStatusError as exc:
            # A real Meta rejection (bad token, closed 24h messaging window,
            # rate limit, ...) must not be swallowed like the network-
            # unreachable case above - re-raise with Meta's own error
            # message so the caller gets a diagnosable failure instead of a
            # raw exception, same convention as `set_ice_breakers`.
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise ValueError(f"Meta rejected the media message send: {detail}") from exc

    async def react_to_message(
        self,
        *,
        instance: ConnectorInstance,
        session: AsyncSession,
        recipient_id: str,
        message_id: str,
        reaction: str = "love",
    ) -> None:
        """React to an inbound DM/story-reply message - the "Auto-React"
        toggle on DM/story-reply/handoff/button-menu automations. Uses the
        Send API's `sender_action: "react"` (confirmed real, Instagram-
        specific - distinct from comment-liking, which is a different,
        Facebook-Page-linked-only capability this codebase deliberately
        doesn't support yet, see `instagram_comment_automation.py`'s
        module docstring). `reaction` is the emoji-name Meta expects
        (e.g. "love", "wow", "sad", "angry", "haha", "like"); `recipient_id`
        must be the ORIGINAL sender's id (the one who sent `message_id`),
        not this account's own id.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        if not instagram_account_id:
            raise RuntimeError(f"connector instance {instance.id} has no instagram_account_id on record")

        # TODO(meta-graph-api): POST /{instagram_account_id}/messages
        #   Authorization: Bearer {access_token}
        #   {"recipient": {"id": "{recipient_id}"}, "sender_action": "react",
        #     "payload": {"message_id": "{message_id}", "reaction": "{reaction}"}}
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    f"/{instagram_account_id}/messages",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    json={
                        "recipient": {"id": recipient_id},
                        "sender_action": "react",
                        "payload": {"message_id": message_id, "reaction": reaction},
                    },
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: skipping this reaction so the "
                "workflow action stays testable offline (instance=%s, message_id=%s).",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
                instance.id,
                message_id,
            )
        except httpx.HTTPStatusError as exc:
            # A real Meta rejection (bad token, closed 24h messaging window,
            # rate limit, ...) must not be swallowed like the network-
            # unreachable case above - re-raise with Meta's own error
            # message so the caller gets a diagnosable failure instead of a
            # raw exception, same convention as `set_ice_breakers`.
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise ValueError(f"Meta rejected the reaction: {detail}") from exc

    async def list_media(
        self,
        *,
        instance: ConnectorInstance,
        session: AsyncSession,
        after: str | None = None,
        limit: int = 25,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """List one page of this account's own posts/reels - the post/reel
        picker for Comment Automation/Comment Moderation's "scope to
        specific posts/reels" option (account-wide, the default, when
        nothing is picked). An account with hundreds of posts can't be
        handed back in one response, so this pages through Meta's own
        cursor (`after`) rather than fetching everything - `limit` per
        page, `after` to continue from a previous call's returned cursor.

        Returns `([], None)` on any stub/unreachable/error condition
        rather than raising - an empty picker (falls back to "every post")
        is a legal state, not an error, same convention as
        `get_ice_breakers`.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return [], None
        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        if not instagram_account_id:
            return [], None

        # TODO(meta-graph-api): GET /{instagram_account_id}/media
        #   ?fields=id,caption,media_type,media_url,thumbnail_url,permalink,timestamp
        #   &limit={limit}&after={after}&access_token={access_token}
        params: dict[str, Any] = {
            "fields": "id,caption,media_type,media_url,thumbnail_url,permalink,timestamp",
            "limit": limit,
        }
        if after:
            params["after"] = after
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.get(
                    f"/{instagram_account_id}/media",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    params=params,
                )
                response.raise_for_status()
                data = response.json()
        except (*_NETWORK_UNREACHABLE_ERRORS, httpx.HTTPStatusError, ValueError) as exc:
            logger.warning(
                "[instagram] could not list media (%s) - returning empty (instance=%s).", exc, instance.id
            )
            return [], None

        next_cursor = ((data.get("paging") or {}).get("cursors") or {}).get("after")
        # Meta still returns a cursor even past the last page - only trust
        # it when `paging.next` (the actual "there IS a next page" signal)
        # is also present, or the picker's "Load more" button would spin
        # forever re-fetching an empty final page.
        if "next" not in (data.get("paging") or {}):
            next_cursor = None
        return list(data.get("data") or []), next_cursor

    async def get_user_profile(
        self, *, instance: ConnectorInstance, session: AsyncSession, user_id: str
    ) -> dict[str, str] | None:
        """Resolve a DM sender's username/name via Meta's Instagram
        Messaging "User Profile API" (`GET /{IGSID}?fields=name,username`) -
        available for any user who has messaged this account, regardless of
        whether they follow it. Instagram's `messaging` webhook payload only
        ever carries the sender's numeric IGSID, unlike a comment webhook
        (which already includes `from.username` inline) - this is the only
        way to turn that id into a display name for the Unified Inbox.

        Returns `None` on any stub/unreachable/error condition rather than
        raising - `inbox_service.upsert_inbound_message`'s lazy resolver
        treats that as "still unknown, try again next message", same
        convention as `list_media`/`get_ice_breakers` returning empty.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return None

        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=10.0) as client:
                response = await client.get(
                    f"/{user_id}",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    params={"fields": "name,username"},
                )
                response.raise_for_status()
                data = response.json()
        except (*_NETWORK_UNREACHABLE_ERRORS, httpx.HTTPStatusError, ValueError) as exc:
            logger.warning(
                "[instagram] could not resolve profile for user %s (%s) - display name stays unset.",
                user_id,
                exc,
            )
            return None

        username = data.get("username")
        name = data.get("name")
        if not username and not name:
            return None
        return {"username": username or "", "name": name or ""}

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
        except httpx.HTTPStatusError as exc:
            # A real Meta rejection (bad token, invalid/deleted comment id,
            # rate limit, ...) must not be swallowed like the network-
            # unreachable case above - re-raise with Meta's own error
            # message so the caller gets a diagnosable failure instead of a
            # raw exception, same convention as `set_ice_breakers`.
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise ValueError(f"Meta rejected the comment reply: {detail}") from exc

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
        except httpx.HTTPStatusError as exc:
            # A real Meta rejection (bad token, invalid/deleted comment id,
            # rate limit, ...) must not be swallowed like the network-
            # unreachable case above - re-raise with Meta's own error
            # message so the caller gets a diagnosable failure instead of a
            # raw exception, same convention as `set_ice_breakers`.
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise ValueError(f"Meta rejected the comment hide: {detail}") from exc

    async def delete_comment(
        self, *, instance: ConnectorInstance, session: AsyncSession, comment_id: str
    ) -> None:
        """Permanently delete an Instagram comment - the `instagram.
        comment_moderation` predefined automation's harder alternative to
        `hide_comment` (hide is reversible and keeps the comment visible to
        its author; delete is not, and removes it outright)."""
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        # TODO(meta-graph-api): DELETE /{comment_id}
        #   Authorization: Bearer {access_token}
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.delete(
                    f"/{comment_id}", headers={"Authorization": f"Bearer {secret['access_token']}"}
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: skipping this delete so the "
                "workflow action stays testable offline (instance=%s, comment_id=%s).",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
                instance.id,
                comment_id,
            )
        except httpx.HTTPStatusError as exc:
            # A real Meta rejection (bad token, invalid/already-deleted
            # comment id, rate limit, ...) must not be swallowed like the
            # network-unreachable case above - re-raise with Meta's own
            # error message so the caller gets a diagnosable failure
            # instead of a raw exception, same convention as
            # `set_ice_breakers`.
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise ValueError(f"Meta rejected the comment delete: {detail}") from exc

    async def send_private_reply(
        self, *, instance: ConnectorInstance, session: AsyncSession, comment_id: str, text: str
    ) -> None:
        """Send a Private Reply: a DM to a comment's author, addressed by
        `comment_id` rather than the author's user id.

        This is the mechanism every "comment X and I'll DM you" flow
        actually uses, and it is NOT interchangeable with
        `send_direct_message`: a Private Reply works on any comment up to
        7 days old, once per comment, even when the commenter has never
        opened a DM thread with this account before - a normal
        `recipient.id` send requires an already-open 24h messaging window,
        which a first-time commenter usually doesn't have. Replaces the
        commenter's-username-as-recipient bug the comment automation's "DM
        Reply" action used to have (Meta's Send API needs a real
        Instagram-scoped id or, for this exact case, a comment_id - never
        a username).
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        if not instagram_account_id:
            raise RuntimeError(f"connector instance {instance.id} has no instagram_account_id on record")

        # TODO(meta-graph-api): POST /{instagram_account_id}/messages
        #   Authorization: Bearer {access_token}
        #   {"recipient": {"comment_id": "{comment_id}"}, "message": {"text": "{text}"}}
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    f"/{instagram_account_id}/messages",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    json={"recipient": {"comment_id": comment_id}, "message": {"text": text}},
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: skipping this private reply so "
                "the workflow action stays testable offline (instance=%s, comment_id=%s).",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
                instance.id,
                comment_id,
            )
        except httpx.HTTPStatusError as exc:
            # A real Meta rejection (bad token, comment older than 7 days,
            # already-replied comment, rate limit, ...) must not be
            # swallowed like the network-unreachable case above - re-raise
            # with Meta's own error message so the caller gets a
            # diagnosable failure instead of a raw exception, same
            # convention as `set_ice_breakers`.
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise ValueError(f"Meta rejected the private reply: {detail}") from exc

    async def send_button_template(
        self,
        *,
        instance: ConnectorInstance,
        session: AsyncSession,
        recipient_id: str,
        text: str,
        buttons: list[dict[str, str]],
    ) -> None:
        """Send every option as postback buttons, in ordered groups of three.

        Meta caps each template at three buttons and titles at 20 characters.
        Subsequent messages use a short continuation prompt. Payloads are never
        shortened: they identify the existing workflow's postback branches.
        """
        if not isinstance(buttons, list) or not buttons or any(
            not isinstance(button, dict)
            or not isinstance(button.get("title"), str) or not button["title"].strip()
            or not isinstance(button.get("payload"), str) or not button["payload"]
            for button in buttons
        ):
            raise ValueError("Button options require non-empty title and payload strings")
        if not isinstance(text, str) or not text.strip() or len(text) > 640:
            raise ValueError("Button prompt must contain between 1 and 640 characters")
        # Validate the complete list before sending any part of the menu.
        normalized = [
            {"type": "postback", "title": button["title"][:20], "payload": button["payload"]}
            for button in buttons
        ]
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        if not instagram_account_id:
            raise RuntimeError(f"connector instance {instance.id} has no instagram_account_id on record")

        delivered = 0
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                for offset in range(0, len(normalized), 3):
                    response = await client.post(
                        f"/{instagram_account_id}/messages",
                        headers={"Authorization": f"Bearer {secret['access_token']}"},
                        json={
                            "recipient": {"id": recipient_id},
                            "message": {
                                "attachment": {
                                    "type": "template",
                                    "payload": {
                                        "template_type": "button",
                                        "text": text if offset == 0 else "More options:",
                                        "buttons": normalized[offset : offset + 3],
                                    },
                                }
                            },
                        },
                    )
                    response.raise_for_status()
                    delivered += 1
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            if delivered:
                raise base.ConnectorActionNotRetryable(
                    "Instagram button menu was partially delivered; not retrying earlier messages"
                ) from exc
            raise
        except httpx.HTTPStatusError as exc:
            # Retrying the whole node after a later message fails would
            # duplicate all the options already delivered to the recipient.
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            if delivered:
                raise base.ConnectorActionNotRetryable(
                    f"Instagram button menu was partially delivered: {detail}"
                ) from exc
            raise ValueError(f"Meta rejected the button template send: {detail}") from exc

    async def send_quick_replies(
        self,
        *,
        instance: ConnectorInstance,
        session: AsyncSession,
        recipient_id: str,
        text: str,
        replies: list[dict[str, str]],
    ) -> None:
        """Send a Quick Replies message: a text prompt with up to 13
        tappable options (Meta's real cap - the Button Template's 3-button
        limit above is per message; that sender batches longer lists). Each reply
        is `{"title": ..., "payload": ...}`; a tap arrives through the
        Messaging webhook as an ordinary `postback` event, identical to a
        button-template tap, so existing postback-routing chains need no
        changes to consume either.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        if not instagram_account_id:
            raise RuntimeError(f"connector instance {instance.id} has no instagram_account_id on record")

        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    f"/{instagram_account_id}/messages",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    json={
                        "recipient": {"id": recipient_id},
                        "message": {
                            "text": text,
                            "quick_replies": [
                                {"content_type": "text", "title": r["title"], "payload": r["payload"]}
                                for r in replies
                            ],
                        },
                    },
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: skipping this quick-replies send so "
                "the workflow action stays testable offline (instance=%s, recipient_id=%s).",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
                instance.id,
                recipient_id,
            )
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise ValueError(f"Meta rejected the quick replies send: {detail}") from exc

    async def set_ice_breakers(
        self, *, instance: ConnectorInstance, session: AsyncSession, questions: list[dict[str, str]]
    ) -> None:
        """Configure up to 4 welcome-menu FAQ buttons shown to a user
        opening a brand-new DM thread with this account for the first time
        - a connector-instance-level *setting*, not a per-message action,
        so it's called from `instagram/router.py`'s dedicated settings
        endpoint, never from `perform_action`/a workflow graph. Each
        question is `{"question": ..., "payload": ...}`; tapping one
        arrives as an ordinary `postback` event, same as a button-template
        tap.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        if not instagram_account_id:
            raise RuntimeError(f"connector instance {instance.id} has no instagram_account_id on record")

        # POST /{instagram_account_id}/messenger_profile - NOT a dedicated
        # `/messenger_ice_breakers` edge (that's the older, Facebook-Page-
        # linked Messenger Platform's endpoint shape - this account uses
        # the standalone "Instagram API with Instagram Login" model, whose
        # Ice Breakers live under the shared `messenger_profile` settings
        # edge instead, gated by the required top-level `"platform":
        # "instagram"` field). Confirmed against Meta's current docs
        # (developers.facebook.com/docs/instagram-platform/instagram-api-
        # with-instagram-login/messaging-api/ice-breakers/) after the
        # previous `/messenger_ice_breakers` shape came back as a genuine
        # Meta rejection ("Object with ID ... does not support this
        # operation"), not a permissions issue.
        #   Authorization: Bearer {access_token}
        #   {"platform": "instagram", "ice_breakers": [{"call_to_actions": [{"question": ..., "payload": ...}, ...],
        #     "locale": "default"}]}
        # Meta enforces one of exactly two keyset shapes per ice_breakers
        # entry - `(question, payload)` flat, or `(call_to_actions,
        # locale)` - and rejects a `call_to_actions` entry with no
        # `locale` (error_subcode 2534058, "Invalid Icebreaker Schema"),
        # confirmed against the real API; the doc example that omits it
        # doesn't match the API's own validation.
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.post(
                    f"/{instagram_account_id}/messenger_profile",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    json={
                        "platform": "instagram",
                        "ice_breakers": [
                            {
                                "call_to_actions": [
                                    {"question": q["question"], "payload": q["payload"]} for q in questions
                                ],
                                "locale": "default",
                            }
                        ],
                    },
                )
                response.raise_for_status()
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[instagram] could not reach %s (%s) - stub mode: skipping ice breaker save so "
                "the settings screen stays testable offline (instance=%s).",
                settings.INSTAGRAM_GRAPH_API_BASE_URL,
                exc,
                instance.id,
            )
        except httpx.HTTPStatusError as exc:
            # Unlike `get_ice_breakers`/`list_media` (read paths, where
            # falling back to an empty result on any failure is a safe,
            # legal state), this is a write called synchronously from
            # `instagram/router.py::set_ice_breakers` - swallowing a real
            # Meta rejection here would tell the settings screen "saved!"
            # when nothing was actually saved. Re-raised as `ValueError`
            # with Meta's own error message so the router can turn it into
            # a real 4xx instead of an unhandled 500 with no detail at all.
            detail = exc.response.text
            try:
                detail = exc.response.json().get("error", {}).get("message", detail)
            except ValueError:
                pass
            raise ValueError(f"Meta rejected the ice breakers update: {detail}") from exc

    async def get_ice_breakers(self, *, instance: ConnectorInstance, session: AsyncSession) -> list[dict[str, str]]:
        """Fetch the currently configured ice breakers, to pre-fill the
        settings screen. Returns `[]` on any stub/unreachable/not-yet-set
        condition rather than raising - an empty welcome menu is a normal,
        legal state, not an error."""
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return []

        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        if not instagram_account_id:
            return []

        # GET /{instagram_account_id}/messenger_profile?fields=ice_breakers -
        # same `messenger_profile` edge `set_ice_breakers` posts to, not a
        # dedicated `/messenger_ice_breakers` edge - see that method's
        # comment for why.
        #   Authorization: Bearer {access_token}
        try:
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.get(
                    f"/{instagram_account_id}/messenger_profile",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    params={"fields": "ice_breakers"},
                )
                response.raise_for_status()
                data = response.json()
        except (*_NETWORK_UNREACHABLE_ERRORS, httpx.HTTPStatusError, ValueError) as exc:
            logger.warning(
                "[instagram] could not fetch ice breakers (%s) - returning empty (instance=%s).",
                exc,
                instance.id,
            )
            return []

        entries = data.get("data") or data.get("ice_breakers") or []
        if not entries:
            return []
        return [
            {"question": cta.get("question", ""), "payload": cta.get("payload", "")}
            for cta in (entries[0].get("call_to_actions") or [])
        ]

    async def _resolve_mention_details(
        self,
        *,
        instance: ConnectorInstance,
        session: AsyncSession,
        media_id: str | None,
        comment_id: str | None,
    ) -> dict[str, Any]:
        """The Mentions webhook only carries `media_id`/`comment_id` - Meta
        requires a second lookup, through the connected account's OWN node,
        to get the actual text/username of a mention (see module
        docstring). Returns `{}` on any failure (never raises) - the
        `instagram.mention_received` trigger still fires with just the raw
        ids on hand; a keyword condition simply won't match without
        resolved text, a safe silent no-op rather than a broken run.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return {}
        instagram_account_id = (instance.provider_ref_ids or {}).get("instagram_account_id")
        if not instagram_account_id:
            return {}

        # TODO(meta-graph-api): GET /{instagram_account_id}?fields=mentioned_comment.comment_id({comment_id}){text,from,media}
        #   or, when there's no comment_id (a caption mention instead):
        #   GET /{instagram_account_id}?fields=mentioned_media.media_id({media_id}){caption,media_url,permalink}
        try:
            if comment_id:
                fields = f"mentioned_comment.comment_id({comment_id}){{text,from,media}}"
            else:
                fields = f"mentioned_media.media_id({media_id}){{caption,media_url,permalink}}"
            async with httpx.AsyncClient(base_url=settings.INSTAGRAM_GRAPH_API_BASE_URL, timeout=15.0) as client:
                response = await client.get(
                    f"/{instagram_account_id}",
                    headers={"Authorization": f"Bearer {secret['access_token']}"},
                    params={"fields": fields},
                )
                response.raise_for_status()
                data = response.json()
        except (*_NETWORK_UNREACHABLE_ERRORS, httpx.HTTPStatusError, ValueError) as exc:
            logger.warning(
                "[instagram] could not resolve mention detail (%s) - firing trigger with raw ids "
                "only (instance=%s, media_id=%s, comment_id=%s).",
                exc,
                instance.id,
                media_id,
                comment_id,
            )
            return {}

        if comment_id:
            comment = data.get("mentioned_comment") or {}
            return {
                "text": comment.get("text"),
                "from_id": (comment.get("from") or {}).get("id"),
                "from_username": (comment.get("from") or {}).get("username"),
            }
        media = data.get("mentioned_media") or {}
        return {"text": media.get("caption"), "permalink": media.get("permalink")}

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
        if action == "send_media_message":
            recipient_id = params.get("recipient_id")
            media_url = params.get("media_url")
            if not recipient_id or not media_url:
                raise ValueError("send_media_message requires non-empty 'recipient_id' and 'media_url' params")
            await self.send_media_message(
                instance=instance,
                session=session,
                recipient_id=recipient_id,
                media_url=media_url,
                media_type=params.get("media_type", "image"),
            )
            return {"recipient_id": recipient_id, "media_url": media_url}
        if action == "react_to_message":
            recipient_id = params.get("recipient_id")
            message_id = params.get("message_id")
            if not recipient_id or not message_id:
                raise ValueError("react_to_message requires non-empty 'recipient_id' and 'message_id' params")
            await self.react_to_message(
                instance=instance,
                session=session,
                recipient_id=recipient_id,
                message_id=message_id,
                reaction=params.get("reaction", "love"),
            )
            return {"recipient_id": recipient_id, "message_id": message_id}
        if action == "reply_to_comment":
            comment_id = params.get("comment_id")
            text = params.get("text")
            if not comment_id or not text:
                raise ValueError("reply_to_comment requires non-empty 'comment_id' and 'text' params")
            await self.reply_to_comment(instance=instance, session=session, comment_id=comment_id, text=text)
            return {"comment_id": comment_id, "text": text}
        if action == "hide_comment":
            comment_id = params.get("comment_id")
            if not comment_id:
                raise ValueError("hide_comment requires a non-empty 'comment_id' param")
            await self.hide_comment(
                instance=instance, session=session, comment_id=comment_id, hidden=params.get("hidden", True)
            )
            return {"comment_id": comment_id}
        if action == "delete_comment":
            comment_id = params.get("comment_id")
            if not comment_id:
                raise ValueError("delete_comment requires a non-empty 'comment_id' param")
            await self.delete_comment(instance=instance, session=session, comment_id=comment_id)
            return {"comment_id": comment_id}
        if action == "send_private_reply":
            comment_id = params.get("comment_id")
            text = params.get("text")
            if not comment_id or not text:
                raise ValueError("send_private_reply requires non-empty 'comment_id' and 'text' params")
            await self.send_private_reply(instance=instance, session=session, comment_id=comment_id, text=text)
            return {"comment_id": comment_id, "text": text}
        if action == "send_button_template":
            recipient_id = params.get("recipient_id")
            text = params.get("text")
            buttons = params.get("buttons")
            if not recipient_id or not text or not buttons:
                raise ValueError("send_button_template requires non-empty 'recipient_id', 'text', and 'buttons' params")
            await self.send_button_template(
                instance=instance, session=session, recipient_id=recipient_id, text=text, buttons=buttons
            )
            return {"recipient_id": recipient_id}
        if action == "send_quick_replies":
            recipient_id = params.get("recipient_id")
            text = params.get("text")
            replies = params.get("replies")
            if not recipient_id or not text or not replies:
                raise ValueError("send_quick_replies requires non-empty 'recipient_id', 'text', and 'replies' params")
            await self.send_quick_replies(
                instance=instance, session=session, recipient_id=recipient_id, text=text, replies=replies
            )
            return {"recipient_id": recipient_id}
        if action == "get_user_profile":
            user_id = params.get("user_id")
            if not user_id:
                raise ValueError("get_user_profile requires a non-empty 'user_id' param")
            profile = await self.get_user_profile(instance=instance, session=session, user_id=user_id)
            # Always both keys present (never a bare `None`), so a
            # downstream node's `{{this_node.username}}` template never
            # breaks on a failed/unreachable lookup - same "empty, not
            # missing" convention `list_media`/`get_ice_breakers` use.
            return {"username": (profile or {}).get("username") or "", "name": (profile or {}).get("name") or ""}
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
            "message": {"mid": "...", "text": "...", "is_echo": true?}}

        `is_echo` (confirmed live: a real webhook delivery for our own
        `send_direct_message` call comes back through this exact same
        webhook) marks a message the connected account itself sent, not
        one it received - skipping it is not just "don't double-count",
        it's load-bearing: a DM auto-reply automation whose reply text
        ever happens to match its own trigger keyword would otherwise
        reply to its own echoed reply forever.

        Also skips a story reply (`message.reply_to.story` set) - that
        routes to `_extract_story_reply`/`instagram.story_reply_received`
        instead, so it doesn't ALSO fire as a plain DM.

        Also skips a Quick Replies tap (`message.quick_reply` set) - Meta
        delivers that as an ordinary message webhook entry too
        (`message.text` is the tapped option's own title, alongside a
        `message.quick_reply.payload` field this method never looks at),
        not a separate event type the way a button-template tap gets its
        own `messaging[].postback` - see `_extract_postback`, which is
        where this routes instead, so a slot/option tap doesn't ALSO fire
        as a plain DM with no `payload` a postback-routing chain could
        branch on.
        """
        entries = body.get("entry") or []
        for entry in entries:
            for messaging in entry.get("messaging") or []:
                message = messaging.get("message")
                if not message or message.get("is_echo"):
                    continue
                if (message.get("reply_to") or {}).get("story"):
                    continue
                if message.get("quick_reply"):
                    continue
                # Instagram can send a second, attachment-only phone card
                # immediately after the number's text message. It has its
                # own mid, so delivery deduplication cannot remove it. This
                # text trigger must not treat that card (or other textless
                # media/status events) as a new message or a collected answer.
                message_text = message.get("text")
                if not isinstance(message_text, str) or not message_text.strip():
                    continue
                return {
                    "from": (messaging.get("sender") or {}).get("id"),
                    "message_id": message.get("mid"),
                    "text": message_text,
                    "timestamp": messaging.get("timestamp"),
                }
        return None

    @staticmethod
    def _extract_story_reply(body: dict[str, Any]) -> dict[str, Any] | None:
        """A DM whose `message.reply_to.story` is set - Instagram's "replied
        to my story" event, delivered through the same Messaging webhook as
        a normal DM (there is no separate webhook field for it), shaped
        `message.reply_to = {"story": {"id": "...", "url": "..."}}`.
        Checked separately from (and takes priority over)
        `_extract_inbound_message` so it fires its own
        `instagram.story_reply_received` trigger instead of a plain DM one.
        """
        entries = body.get("entry") or []
        for entry in entries:
            for messaging in entry.get("messaging") or []:
                message = messaging.get("message")
                if not message or message.get("is_echo"):
                    continue
                story = (message.get("reply_to") or {}).get("story")
                if not story:
                    continue
                return {
                    "from": (messaging.get("sender") or {}).get("id"),
                    "message_id": message.get("mid"),
                    "text": message.get("text"),
                    "story_id": story.get("id"),
                }
        return None

    @staticmethod
    def _extract_postback(body: dict[str, Any]) -> dict[str, Any] | None:
        """A tap on a button-template or ice-breaker button - arrives as
        `messaging[].postback = {"mid": ..., "payload": ..., "title": ...}`,
        a sibling field to `.message` on the same Messaging webhook (never
        both on the same entry).

        `postback.mid` IS a real, stable id (confirmed live: Meta
        redelivers the identical event - same `mid`, same top-level
        `timestamp` - multiple times, ~20s apart, when our response
        takes too long) - it must be used as the trigger's dedupe key,
        exactly like a normal message's `message.mid`. An earlier version
        of this method assumed no stable id existed here and left it
        undeduplicated, which meant every one of Meta's retries fired its
        own workflow run - a single button tap producing several replies.

        Also recognizes a Quick Replies tap - a *different* wire shape
        (`messaging[].message = {"mid": ..., "text": <title>,
        "quick_reply": {"payload": ...}}`, not a `.postback` field at
        all), but the exact same trigger-side event conceptually (a tap
        that must carry a `payload` a routing chain can branch on) - so
        this normalizes both into one `{from, payload, title, mid}` shape
        and fires as `instagram.postback_received` either way. This is
        deliberately NOT split into a separate trigger type: every
        existing/future postback-routing chain in this codebase branches
        on `trigger.payload` prefixes, and neither the graph author nor
        the customer cares which Meta message type happened to render the
        options, only which one they tapped.
        """
        entries = body.get("entry") or []
        for entry in entries:
            for messaging in entry.get("messaging") or []:
                postback = messaging.get("postback")
                if postback:
                    return {
                        "from": (messaging.get("sender") or {}).get("id"),
                        "payload": postback.get("payload"),
                        "title": postback.get("title"),
                        "mid": postback.get("mid"),
                        "timestamp": messaging.get("timestamp"),
                    }
                message = messaging.get("message")
                quick_reply = (message or {}).get("quick_reply")
                if message and quick_reply and not message.get("is_echo"):
                    return {
                        "from": (messaging.get("sender") or {}).get("id"),
                        "payload": quick_reply.get("payload"),
                        "title": message.get("text"),
                        "mid": message.get("mid"),
                        "timestamp": messaging.get("timestamp"),
                    }
        return None

    @staticmethod
    def _extract_referral(body: dict[str, Any]) -> dict[str, Any] | None:
        """An ad-click or ig.me-shortlink-originated conversation start -
        `messaging[].referral` (a fresh conversation with no prior message)
        or `messaging[].postback.referral`/`messaging[].message` alongside
        a `referral` key (an in-context referral attached to the first
        real message) - checked independently of, and not mutually
        exclusive with, `_extract_inbound_message`/`_extract_postback`.

        Unlike a message or postback, a referral event carries no `mid` of
        its own - `timestamp` (present on every Messaging webhook entry,
        confirmed live alongside `postback.mid`) is captured here instead,
        so the caller can build a synthetic dedupe key from
        `(sender, ref, timestamp)` and avoid the exact same
        redelivery-causes-duplicate-runs bug `_extract_postback`'s
        docstring describes.
        """
        entries = body.get("entry") or []
        for entry in entries:
            for messaging in entry.get("messaging") or []:
                referral = messaging.get("referral") or (messaging.get("postback") or {}).get("referral")
                if not referral:
                    continue
                return {
                    "from": (messaging.get("sender") or {}).get("id"),
                    "ref": referral.get("ref"),
                    "source": referral.get("source"),
                    "ad_id": referral.get("ad_id"),
                    "timestamp": messaging.get("timestamp"),
                }
        return None

    @staticmethod
    def _extract_message_reaction(body: dict[str, Any]) -> dict[str, Any] | None:
        """A reaction (Instagram's Send API only supports "love" outbound,
        but any emoji can arrive inbound) added to a previously-sent
        message - `messaging[].reaction = {"mid": ..., "action":
        "react"|"unreact", "reaction": "love", "emoji": "..."}`."""
        entries = body.get("entry") or []
        for entry in entries:
            for messaging in entry.get("messaging") or []:
                reaction = messaging.get("reaction")
                if not reaction:
                    continue
                return {
                    "from": (messaging.get("sender") or {}).get("id"),
                    "message_id": reaction.get("mid"),
                    "action": reaction.get("action"),
                    "reaction": reaction.get("reaction"),
                }
        return None

    @staticmethod
    def _extract_mention(body: dict[str, Any]) -> dict[str, Any] | None:
        """Someone `@mentions` this account in a comment or caption on
        media THEY own (not this account's own media - that's
        `_extract_inbound_comment`'s job). Real shape (Meta docs):
          entry[0].changes[0] = {"field": "mentions", "value":
            {"media_id": "...", "comment_id": "..." (only for a comment
            mention - absent for a caption mention)}}
        Only carries ids; `_resolve_mention_details` does the follow-up
        lookup for the actual text/username."""
        entries = body.get("entry") or []
        for entry in entries:
            for change in entry.get("changes") or []:
                if change.get("field") != "mentions":
                    continue
                value = change.get("value") or {}
                if not value.get("media_id"):
                    continue
                return value
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
            # Decide resume versus new flow in the ordered dispatcher. Doing
            # it here would bind a fast-following Hi to the pre-/clear run
            # before the queued reset has had a chance to cancel that run.
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="instagram.message_received",
                payload=inbound_message,
                connector_instance_id=instance.id,
                dedupe_key=inbound_message.get("message_id"),
            )
            # Unified Inbox: DMs only - comments (below) aren't a
            # "conversation" in the inbox sense. Recorded regardless of
            # resume-vs-trigger above - the inbox is a plain message log,
            # not aware of the workflow engine's suspend/resume state.
            if inbound_message.get("text"):
                sender_id = inbound_message.get("from")

                async def _resolve_display_name() -> str | None:
                    profile = await self.get_user_profile(instance=instance, session=session, user_id=sender_id)
                    if profile is None:
                        return None
                    return profile.get("username") or profile.get("name") or None

                await inbox_service.upsert_inbound_message(
                    session,
                    instance=instance,
                    external_contact_id=sender_id,
                    content=inbound_message.get("text"),
                    external_message_id=inbound_message.get("message_id"),
                    resolve_display_name=_resolve_display_name,
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
                    "from_id": (inbound_comment.get("from") or {}).get("id"),
                    "from_username": (inbound_comment.get("from") or {}).get("username"),
                    "media_id": (inbound_comment.get("media") or {}).get("id"),
                },
                connector_instance_id=instance.id,
                dedupe_key=inbound_comment["id"],
            )

        inbound_story_reply = self._extract_story_reply(body)
        if inbound_story_reply is not None:
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="instagram.story_reply_received",
                payload={
                    "from": inbound_story_reply.get("from"),
                    "message_id": inbound_story_reply.get("message_id"),
                    "text": inbound_story_reply.get("text"),
                    "story_id": inbound_story_reply.get("story_id"),
                },
                connector_instance_id=instance.id,
                dedupe_key=inbound_story_reply.get("message_id"),
            )

        inbound_postback = self._extract_postback(body)
        if inbound_postback is not None:
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="instagram.postback_received",
                payload={
                    "from": inbound_postback.get("from"),
                    "payload": inbound_postback.get("payload"),
                    "title": inbound_postback.get("title"),
                    "timestamp": inbound_postback.get("timestamp"),
                },
                connector_instance_id=instance.id,
                # `postback.mid` IS a stable id (see `_extract_postback`'s
                # docstring - Meta redelivers the identical event on a
                # slow response) - a real production bug when this was
                # left `None`: one button tap fired a workflow run per
                # retry, each sending its own reply.
                dedupe_key=inbound_postback.get("mid"),
            )

        inbound_referral = self._extract_referral(body)
        if inbound_referral is not None:
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="instagram.referral_received",
                payload={
                    "from": inbound_referral.get("from"),
                    "ref": inbound_referral.get("ref"),
                    "source": inbound_referral.get("source"),
                    "ad_id": inbound_referral.get("ad_id"),
                },
                connector_instance_id=instance.id,
                # No `mid` of its own (see `_extract_referral`'s
                # docstring) - a synthetic key from sender+ref+timestamp
                # still catches the same class of Meta-redelivery bug
                # `_extract_postback`'s dedupe fix addresses, without
                # needing a real id that doesn't exist here.
                dedupe_key=(
                    f"{inbound_referral.get('from')}:{inbound_referral.get('ref')}:{inbound_referral.get('timestamp')}"
                    if inbound_referral.get("timestamp")
                    else None
                ),
            )

        inbound_reaction = self._extract_message_reaction(body)
        if inbound_reaction is not None:
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="instagram.message_reaction_received",
                payload={
                    "from": inbound_reaction.get("from"),
                    "message_id": inbound_reaction.get("message_id"),
                    "action": inbound_reaction.get("action"),
                    "reaction": inbound_reaction.get("reaction"),
                },
                connector_instance_id=instance.id,
                dedupe_key=(
                    f"{inbound_reaction.get('message_id')}:{inbound_reaction.get('action')}"
                    if inbound_reaction.get("message_id")
                    else None
                ),
            )

        inbound_mention = self._extract_mention(body)
        if inbound_mention is not None:
            details = await self._resolve_mention_details(
                instance=instance,
                session=session,
                media_id=inbound_mention.get("media_id"),
                comment_id=inbound_mention.get("comment_id"),
            )
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="instagram.mention_received",
                payload={
                    "media_id": inbound_mention.get("media_id"),
                    "comment_id": inbound_mention.get("comment_id"),
                    "text": details.get("text"),
                    "from_id": details.get("from_id"),
                    "from_username": details.get("from_username"),
                },
                connector_instance_id=instance.id,
                dedupe_key=inbound_mention.get("comment_id") or inbound_mention.get("media_id"),
            )

        return [event]


adapter = InstagramAdapter()
base.registry.register(adapter)
