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
from typing import Any, Literal, Mapping
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

    async def _post_message(
        self, *, instance: ConnectorInstance, session: AsyncSession, message_payload: dict[str, Any]
    ) -> None:
        """Shared POST /{phone_number_id}/messages call, factored out of
        `send_text_message` so the five newer send methods below don't each
        repeat the credential/phone-number-id lookup and stub-mode check.
        `message_payload` is everything after `messaging_product`/
        `recipient_type`/`to` - i.e. just the `type`+type-specific keys."""
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")

        phone_number_id = (instance.provider_ref_ids or {}).get("phone_number_id")
        if not phone_number_id:
            raise RuntimeError(f"connector instance {instance.id} has no phone_number_id on record")

        async with httpx.AsyncClient(base_url=settings.WHATSAPP_GRAPH_API_BASE_URL, timeout=15.0) as client:
            response = await client.post(
                f"/{phone_number_id}/messages",
                headers={"Authorization": f"Bearer {secret['access_token']}"},
                json={"messaging_product": "whatsapp", **message_payload},
            )
            response.raise_for_status()

    async def send_media_message(
        self,
        *,
        instance: ConnectorInstance,
        to: str,
        media_type: Literal["image", "video", "audio", "document"],
        media_url: str | None = None,
        media_id: str | None = None,
        caption: str | None = None,
        filename: str | None = None,
        session: AsyncSession,
    ) -> None:
        """Session (free-form) media message - only deliverable within the
        24-hour customer service window, same as `send_text_message`; Meta
        rejects it outside that window and the caller sees that as a clean
        adapter-raised error, not a silent failure (see module docstring's
        "let the provider be the source of truth" convention)."""
        if not media_url and not media_id:
            raise ValueError("send_media_message requires either media_url or media_id")
        if not settings.whatsapp_configured:
            logger.warning(
                "[whatsapp] stub mode - skipping media send (instance=%s, to=%s, media_type=%s)",
                instance.id, to, media_type,
            )
            return

        # TODO(meta-graph-api): POST /{phone_number_id}/messages
        #   {"messaging_product":"whatsapp","to":"{to}","type":"{media_type}",
        #    "{media_type}": {"link": "{media_url}"} | {"id": "{media_id}"},
        #    caption/filename as applicable}
        media_object: dict[str, Any] = {"link": media_url} if media_url else {"id": media_id}
        if caption and media_type in ("image", "video", "document"):
            media_object["caption"] = caption
        if filename and media_type == "document":
            media_object["filename"] = filename
        await self._post_message(
            instance=instance, session=session,
            message_payload={"to": to, "type": media_type, media_type: media_object},
        )

    async def send_location_message(
        self,
        *,
        instance: ConnectorInstance,
        to: str,
        latitude: float,
        longitude: float,
        name: str | None = None,
        address: str | None = None,
        session: AsyncSession,
    ) -> None:
        if not settings.whatsapp_configured:
            logger.warning("[whatsapp] stub mode - skipping location send (instance=%s, to=%s)", instance.id, to)
            return
        # TODO(meta-graph-api): POST /{phone_number_id}/messages
        #   {"type":"location","location":{"latitude":..,"longitude":..,"name":..,"address":..}}
        location: dict[str, Any] = {"latitude": latitude, "longitude": longitude}
        if name:
            location["name"] = name
        if address:
            location["address"] = address
        await self._post_message(
            instance=instance, session=session,
            message_payload={"to": to, "type": "location", "location": location},
        )

    async def send_contact_message(
        self,
        *,
        instance: ConnectorInstance,
        to: str,
        contacts: list[dict[str, str]],
        session: AsyncSession,
    ) -> None:
        """`contacts`: `[{"name": str, "phone": str}, ...]` - a simplified
        subset of Meta's much richer vCard-like contact object (which also
        supports emails/orgs/addresses/birthday); extend here if a real use
        case needs more than name+phone."""
        if not settings.whatsapp_configured:
            logger.warning("[whatsapp] stub mode - skipping contact send (instance=%s, to=%s)", instance.id, to)
            return
        # TODO(meta-graph-api): POST /{phone_number_id}/messages
        #   {"type":"contacts","contacts":[{"name":{"formatted_name":..},"phones":[{"phone":..}]}]}
        payload_contacts = [
            {
                "name": {"formatted_name": c["name"], "first_name": c["name"]},
                "phones": [{"phone": c["phone"]}],
            }
            for c in contacts
        ]
        await self._post_message(
            instance=instance, session=session,
            message_payload={"to": to, "type": "contacts", "contacts": payload_contacts},
        )

    async def send_interactive_message(
        self,
        *,
        instance: ConnectorInstance,
        to: str,
        body_text: str,
        interactive_type: Literal["button", "list"],
        buttons: list[dict[str, str]] | None = None,
        list_button_label: str | None = None,
        sections: list[dict[str, Any]] | None = None,
        session: AsyncSession,
    ) -> None:
        """Session message. `buttons`: up to 3 `{"id","title"}` quick-reply
        buttons. `sections` (list mode): up to 10 rows total across all
        sections, each `{"title","rows":[{"id","title","description"}]}` -
        both are Meta's own hard limits, not this adapter's; a request
        exceeding them is rejected by Meta and surfaces as a clean error."""
        if not settings.whatsapp_configured:
            logger.warning(
                "[whatsapp] stub mode - skipping interactive send (instance=%s, to=%s, type=%s)",
                instance.id, to, interactive_type,
            )
            return

        # TODO(meta-graph-api): POST /{phone_number_id}/messages
        #   {"type":"interactive","interactive":{"type":"button"|"list", "body":{"text":..},
        #    "action":{"buttons":[...]} | {"button":.., "sections":[...]}}}
        action: dict[str, Any]
        if interactive_type == "button":
            action = {"buttons": [{"type": "reply", "reply": {"id": b["id"], "title": b["title"]}} for b in (buttons or [])]}
        else:
            action = {"button": list_button_label or "Choose", "sections": sections or []}
        await self._post_message(
            instance=instance, session=session,
            message_payload={
                "to": to,
                "type": "interactive",
                "interactive": {"type": interactive_type, "body": {"text": body_text}, "action": action},
            },
        )

    async def send_product_list_message(
        self,
        *,
        instance: ConnectorInstance,
        to: str,
        catalog_id: str,
        body_text: str,
        sections: list[dict[str, Any]],
        footer_text: str | None = None,
        header_text: str | None = None,
        session: AsyncSession,
    ) -> None:
        """Session message: WhatsApp's Commerce Catalog "product list"
        interactive message - shows the customer a curated set of items
        from a Meta Commerce Catalog already connected to this WABA (that
        connection is made entirely on Meta's side via Commerce Manager /
        Embedded Signup; this codebase has no catalog-management surface
        of its own and never will for v1). The customer can add any number
        of the listed items to a cart and submit it as a single message -
        the genuine multi-select capability `whatsapp.ask_choice`'s
        button/list messages cannot offer (those are always single-tap,
        single-select). `sections`: up to 10 sections, 30 `product_items`
        total across all of them - Meta's own hard limits, not this
        adapter's.

        Cart-to-catalog matching convention (deliberate MVP scope
        boundary, not an oversight): each `product_retailer_id` sent here
        must equal the corresponding `ProductService.id` (its UUID, as a
        string) as configured on the Meta Commerce Catalog side. No
        separate id-mapping table exists or is planned - the tenant is
        responsible for setting each catalog product's retailer id to
        match its id in this system when they build/sync their Meta
        catalog feed.
        """
        if not settings.whatsapp_configured:
            logger.warning(
                "[whatsapp] stub mode - skipping product list send (instance=%s, to=%s, catalog=%s)",
                instance.id, to, catalog_id,
            )
            return

        # TODO(meta-graph-api): POST /{phone_number_id}/messages
        #   {"type":"interactive","interactive":{"type":"product_list",
        #    "header":{"type":"text","text":..}?, "body":{"text":..}, "footer":{"text":..}?,
        #    "action":{"catalog_id":.., "sections":[{"title":..,"product_items":[{"product_retailer_id":..}]}]}}}
        interactive: dict[str, Any] = {
            "type": "product_list",
            "body": {"text": body_text},
            "action": {"catalog_id": catalog_id, "sections": sections},
        }
        if header_text:
            interactive["header"] = {"type": "text", "text": header_text}
        if footer_text:
            interactive["footer"] = {"text": footer_text}
        await self._post_message(
            instance=instance, session=session,
            message_payload={"to": to, "type": "interactive", "interactive": interactive},
        )

    async def send_template_message(
        self,
        *,
        instance: ConnectorInstance,
        to: str,
        template_name: str,
        language_code: str,
        header_variable: str | None = None,
        body_variables: list[str] | None = None,
        session: AsyncSession,
    ) -> None:
        """Template (HSM) message - the only kind sendable outside the
        24-hour customer service window, and the only kind Meta requires
        pre-approval for (marketing/utility/authentication - see
        `whatsapp/models.py::WhatsAppTemplate`). `template_name`/
        `language_code` must match an approved template exactly; Meta
        rejects an unknown/mismatched one, surfaced as a clean adapter
        error rather than silently no-opping."""
        if not settings.whatsapp_configured:
            logger.warning(
                "[whatsapp] stub mode - skipping template send (instance=%s, to=%s, template=%s/%s)",
                instance.id, to, template_name, language_code,
            )
            return

        # TODO(meta-graph-api): POST /{phone_number_id}/messages
        #   {"type":"template","template":{"name":..,"language":{"code":..},
        #    "components":[{"type":"header","parameters":[...]}, {"type":"body","parameters":[...]}]}}
        components: list[dict[str, Any]] = []
        if header_variable:
            components.append({"type": "header", "parameters": [{"type": "text", "text": header_variable}]})
        if body_variables:
            components.append(
                {"type": "body", "parameters": [{"type": "text", "text": v} for v in body_variables]}
            )
        await self._post_message(
            instance=instance, session=session,
            message_payload={
                "to": to,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": language_code},
                    **({"components": components} if components else {}),
                },
            },
        )

    async def sync_templates(self, *, instance: ConnectorInstance, session: AsyncSession) -> list[dict[str, Any]]:
        """Pull this WABA's approved/pending/rejected message templates from
        Meta - `whatsapp/service.py::sync_from_meta` upserts the result into
        the local `WhatsAppTemplate` catalog. Stubbed the same way as every
        other real call in this file when no app is configured, returning a
        small canned example so the catalog/sync UI stays testable without
        real Meta credentials."""
        if not settings.whatsapp_configured:
            logger.warning("[whatsapp] stub mode - returning canned example templates for sync")
            return [
                {
                    "name": "order_confirmation",
                    "language": "en_US",
                    "category": "utility",
                    "status": "approved",
                    "components": [
                        {"type": "BODY", "text": "Hi {{1}}, your order {{2}} has been confirmed!"},
                    ],
                },
                {
                    "name": "weekend_sale",
                    "language": "en_US",
                    "category": "marketing",
                    "status": "approved",
                    "components": [
                        {"type": "BODY", "text": "{{1}}, enjoy 20% off this weekend only!"},
                    ],
                },
            ]

        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")
        waba_id = (instance.provider_ref_ids or {}).get("waba_id")
        # TODO(meta-graph-api): GET /{waba_id}/message_templates
        async with httpx.AsyncClient(base_url=settings.WHATSAPP_GRAPH_API_BASE_URL, timeout=15.0) as client:
            response = await client.get(
                f"/{waba_id}/message_templates", params={"access_token": secret["access_token"]}
            )
            response.raise_for_status()
            return response.json().get("data", [])

    async def mark_message_as_read(
        self, *, instance: ConnectorInstance, message_id: str, session: AsyncSession
    ) -> None:
        """Mark an inbound message as read (blue ticks) - `whatsapp.mark_as_read`
        workflow node, typically called with `{{trigger.message_id}}`."""
        if not settings.whatsapp_configured:
            logger.warning(
                "[whatsapp] stub mode - skipping mark-as-read (instance=%s, message_id=%s)",
                instance.id, message_id,
            )
            return
        # TODO(meta-graph-api): POST /{phone_number_id}/messages
        #   {"messaging_product":"whatsapp","status":"read","message_id":"{message_id}"}
        await self._post_message(
            instance=instance, session=session,
            message_payload={"status": "read", "message_id": message_id},
        )

    async def get_business_profile(
        self, *, instance: ConnectorInstance, session: AsyncSession
    ) -> dict[str, Any]:
        """`whatsapp.get_business_profile` workflow node. Stub mode returns a
        small canned profile so the node is testable without real credentials,
        matching `sync_templates`'s convention."""
        if not settings.whatsapp_configured:
            logger.warning("[whatsapp] stub mode - returning canned business profile")
            return {
                "about": "stub business profile",
                "address": "",
                "description": "",
                "email": "",
                "profile_picture_url": "",
                "websites": [],
                "vertical": "OTHER",
            }

        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")
        phone_number_id = (instance.provider_ref_ids or {}).get("phone_number_id")
        if not phone_number_id:
            raise RuntimeError(f"connector instance {instance.id} has no phone_number_id on record")

        # TODO(meta-graph-api): GET /{phone_number_id}/whatsapp_business_profile
        #   ?fields=about,address,description,email,profile_picture_url,websites,vertical
        async with httpx.AsyncClient(base_url=settings.WHATSAPP_GRAPH_API_BASE_URL, timeout=15.0) as client:
            response = await client.get(
                f"/{phone_number_id}/whatsapp_business_profile",
                params={
                    "fields": "about,address,description,email,profile_picture_url,websites,vertical",
                    "access_token": secret["access_token"],
                },
            )
            response.raise_for_status()
            data = response.json().get("data", [])
            return data[0] if data else {}

    async def update_business_profile(
        self, *, instance: ConnectorInstance, profile_fields: dict[str, Any], session: AsyncSession
    ) -> dict[str, Any]:
        """`whatsapp.update_business_profile` workflow node. `profile_fields`
        may set any of `about`/`address`/`description`/`email`/`websites`/
        `vertical` - passed through as-is, Meta validates the shape."""
        if not settings.whatsapp_configured:
            logger.warning(
                "[whatsapp] stub mode - skipping business profile update (instance=%s, fields=%s)",
                instance.id, sorted(profile_fields),
            )
            return {**profile_fields}

        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise RuntimeError(f"no credential stored for connector instance {instance.id}")
        phone_number_id = (instance.provider_ref_ids or {}).get("phone_number_id")
        if not phone_number_id:
            raise RuntimeError(f"connector instance {instance.id} has no phone_number_id on record")

        # TODO(meta-graph-api): POST /{phone_number_id}/whatsapp_business_profile
        #   {"messaging_product":"whatsapp", ...profile_fields}
        async with httpx.AsyncClient(base_url=settings.WHATSAPP_GRAPH_API_BASE_URL, timeout=15.0) as client:
            response = await client.post(
                f"/{phone_number_id}/whatsapp_business_profile",
                headers={"Authorization": f"Bearer {secret['access_token']}"},
                json={"messaging_product": "whatsapp", **profile_fields},
            )
            response.raise_for_status()
        return profile_fields

    async def perform_action(
        self, *, action: str, params: dict[str, Any], instance: ConnectorInstance, session: AsyncSession
    ) -> dict[str, Any]:
        """Dispatch for the generic `connector.action` workflow node type
        (see `base.ConnectorAdapter.perform_action`'s docstring) - kept as
        the low-level escape hatch even though WhatsApp's primary send
        capabilities now have their own dedicated, well-typed node
        executors (`modules/workflows/nodes/whatsapp_send_*.py`) rather
        than being reached only through this generic dispatch. A future
        new capability is still one more `elif` branch here first."""
        if action == "send_text_message":
            to = params.get("to")
            body = params.get("body")
            if not to or not body:
                raise ValueError("send_text_message requires non-empty 'to' and 'body' params")
            await self.send_text_message(instance=instance, to=to, body=body, session=session)
            return {"to": to, "body": body}
        if action == "send_media_message":
            await self.send_media_message(
                instance=instance,
                to=params["to"],
                media_type=params["media_type"],
                media_url=params.get("media_url"),
                media_id=params.get("media_id"),
                caption=params.get("caption"),
                filename=params.get("filename"),
                session=session,
            )
            return {"to": params["to"], "media_type": params["media_type"]}
        if action == "send_location_message":
            await self.send_location_message(
                instance=instance,
                to=params["to"],
                latitude=params["latitude"],
                longitude=params["longitude"],
                name=params.get("name"),
                address=params.get("address"),
                session=session,
            )
            return {"to": params["to"]}
        if action == "send_contact_message":
            await self.send_contact_message(
                instance=instance, to=params["to"], contacts=params["contacts"], session=session
            )
            return {"to": params["to"]}
        if action == "send_interactive_message":
            await self.send_interactive_message(
                instance=instance,
                to=params["to"],
                body_text=params["body_text"],
                interactive_type=params["interactive_type"],
                buttons=params.get("buttons"),
                list_button_label=params.get("list_button_label"),
                sections=params.get("sections"),
                session=session,
            )
            return {"to": params["to"]}
        if action == "send_template_message":
            await self.send_template_message(
                instance=instance,
                to=params["to"],
                template_name=params["template_name"],
                language_code=params["language_code"],
                header_variable=params.get("header_variable"),
                body_variables=params.get("body_variables"),
                session=session,
            )
            return {"to": params["to"], "template_name": params["template_name"]}
        if action == "mark_message_as_read":
            message_id = params.get("message_id")
            if not message_id:
                raise ValueError("mark_message_as_read requires a non-empty 'message_id' param")
            await self.mark_message_as_read(instance=instance, message_id=message_id, session=session)
            return {"message_id": message_id}
        if action == "get_business_profile":
            return await self.get_business_profile(instance=instance, session=session)
        if action == "update_business_profile":
            return await self.update_business_profile(
                instance=instance, profile_fields=params.get("profile_fields", {}), session=session
            )
        raise NotImplementedError(f"{self.connector_type_key} does not support action {action!r}")

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
        (`.statuses`, see `_extract_status_update`) or otherwise doesn't
        carry a `.messages` entry.

        Enriched beyond plain text to also surface, per `message.type`
        (Meta docs shapes):
          - `interactive`: `message.interactive.button_reply` or
            `.list_reply`, each `{"id","title"}` - a workflow trigger
            distinguishes this via `message_type == "interactive"` (see
            `handle_webhook`'s routing to `whatsapp.interactive_reply_received`).
          - `image`/`video`/`audio`/`document`: `message.{type}` =
            `{"id","mime_type","caption"?,"filename"?}`.
          - `location`: `message.location` = `{"latitude","longitude","name"?,"address"?}`.
          - `contacts`: `message.contacts` (Meta's own list-of-vCard-like shape, passed through as-is).
          - `order`: a submitted WhatsApp Commerce Catalog cart (sent in
            reply to a `whatsapp.ask_for_cart` product-list message, never
            spontaneously) - `message.order` = `{"catalog_id", "product_items":
            [{"product_retailer_id","quantity","item_price","currency"}, ...],
            "text"?}`. Surfaced as `message.order.{catalog_id,product_items,note}`
            (renaming Meta's own optional cart-note field `text` to `note`
            here, since `extracted["text"]` above is already reserved for a
            plain text message body and would otherwise collide in meaning).
            No dedicated trigger type - resuming a suspended `whatsapp.
            ask_for_cart` run is `handle_webhook`'s only consumer of this,
            via the same `find_pending_wait` correlation every other reply
            type already uses.
        """
        entries = body.get("entry") or []
        for entry in entries:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                messages = value.get("messages") or []
                if not messages:
                    continue
                message = messages[0]
                message_type = message.get("type")
                extracted: dict[str, Any] = {
                    "from": message.get("from"),
                    "message_id": message.get("id"),
                    "message_type": message_type,
                    "text": (message.get("text") or {}).get("body"),
                    "timestamp": message.get("timestamp"),
                }
                if message_type == "interactive":
                    interactive = message.get("interactive") or {}
                    reply = interactive.get("button_reply") or interactive.get("list_reply")
                    if reply:
                        extracted["interactive"] = {
                            "type": "button_reply" if "button_reply" in interactive else "list_reply",
                            "id": reply.get("id"),
                            "title": reply.get("title"),
                        }
                elif message_type in ("image", "video", "audio", "document"):
                    media = message.get(message_type) or {}
                    extracted["media"] = {
                        "id": media.get("id"),
                        "mime_type": media.get("mime_type"),
                        "caption": media.get("caption"),
                        "filename": media.get("filename"),
                    }
                elif message_type == "location":
                    extracted["location"] = message.get("location")
                elif message_type == "contacts":
                    extracted["contacts"] = message.get("contacts")
                elif message_type == "order":
                    order = message.get("order") or {}
                    extracted["order"] = {
                        "catalog_id": order.get("catalog_id"),
                        "product_items": order.get("product_items") or [],
                        "note": order.get("text"),
                    }
                return extracted
        return None

    @staticmethod
    def _extract_status_update(body: dict[str, Any]) -> dict[str, Any] | None:
        """Pull the first delivery-status callback out of a webhook body -
        Meta's `.statuses` array, sent for every outbound message
        (including template sends) as it moves through
        sent -> delivered -> read (or -> failed), independent of the
        `.messages` array `_extract_inbound_message` reads. This is what
        makes marketing/utility delivery tracking possible.

        Real shape (Meta docs):
          entry[0].changes[0].value.statuses[0] = {
            "id": "<message_id>", "status": "sent"|"delivered"|"read"|"failed",
            "timestamp": "...", "recipient_id": "<wa_id>", "errors": [...]?
          }
        """
        entries = body.get("entry") or []
        for entry in entries:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                statuses = value.get("statuses") or []
                if not statuses:
                    continue
                status = statuses[0]
                errors = status.get("errors") or []
                return {
                    "message_id": status.get("id"),
                    "status": status.get("status"),
                    "recipient_id": status.get("recipient_id"),
                    "timestamp": status.get("timestamp"),
                    "error": errors[0].get("message") if errors else None,
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
        # its built-in nodes, one of which (`send_whatsapp_message`)
        # imports *this* module for the `adapter` singleton - importing
        # `event_bus` at module level here would be a circular import.
        from fusionflow.modules.workflows.engine import event_bus

        inbound_message = self._extract_inbound_message(body)
        if inbound_message is not None:
            # Phase 8 Part A: if this customer already has a run paused
            # waiting for exactly their next reply (on this connector
            # instance), this message resumes that run instead of firing a
            # brand-new trigger - a second inbound message from the same
            # customer while a run is waiting always continues that same
            # conversation, never starts a parallel one.
            pending_run = await event_bus.find_pending_wait(
                session,
                tenant_id=instance.tenant_id,
                connector_instance_id=instance.id,
                correlation_key=inbound_message.get("from"),
            )
            if pending_run is not None:
                await event_bus.publish_resume_event(
                    session,
                    run=pending_run,
                    reply_payload=inbound_message,
                    dedupe_key=inbound_message.get("message_id"),
                )
            else:
                # An interactive reply (button/list tap) gets its own dedicated
                # trigger type rather than the generic `whatsapp.message_received`
                # - exclusive routing, not additive, since this payload shape
                # (`message_type == "interactive"`) was never populated before
                # this phase, so no existing workflow depends on seeing it via
                # the generic trigger.
                event_type = (
                    "whatsapp.interactive_reply_received"
                    if inbound_message.get("message_type") == "interactive"
                    else "whatsapp.message_received"
                )
                # Same transaction/session as the ConnectorEvent write above -
                # the outbox row and the audit row commit together or not at
                # all (transactional outbox, see event_bus.py). The caller
                # (webhooks.py) commits once after this returns.
                # `message_id` is WhatsApp's own delivery id - Meta redelivers
                # webhooks on a missed/slow ack, and this dedupe_key is what
                # stops a redelivery from firing the workflow a second time
                # (see event_bus.publish_trigger_event's docstring).
                await event_bus.publish_trigger_event(
                    session,
                    tenant_id=instance.tenant_id,
                    event_type=event_type,
                    payload=inbound_message,
                    connector_instance_id=instance.id,
                    dedupe_key=inbound_message.get("message_id"),
                )

        status_update = self._extract_status_update(body)
        if status_update is not None:
            # dedupe_key includes the status itself: Meta can (and does)
            # send a separate callback per status transition
            # (sent/delivered/read/failed) for the SAME message_id, and
            # each is a distinct, real event this trigger should fire for
            # - only an exact redelivery of the identical status should be
            # deduped, not the natural sent->delivered->read progression.
            await event_bus.publish_trigger_event(
                session,
                tenant_id=instance.tenant_id,
                event_type="whatsapp.message_status_updated",
                payload=status_update,
                connector_instance_id=instance.id,
                dedupe_key=f"{status_update.get('message_id')}:{status_update.get('status')}",
            )

        return [event]


adapter = WhatsAppAdapter()
base.registry.register(adapter)
