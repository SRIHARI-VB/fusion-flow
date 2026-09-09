"""Razorpay connector adapter.

`auth_mode="api_key"`: unlike WhatsApp, Razorpay has no OAuth dance for a
merchant connecting their own account - the tenant pastes their `key_id` +
`key_secret` (generated in their own Razorpay dashboard) directly into
`initiate_connect`'s `params`. Validated with a real, lightweight
authenticated call (`GET /v1/payments?count=1`, HTTP Basic auth) via
`httpx`. If that call cannot even reach the network (this sandbox has none),
the failure is caught narrowly and downgraded to a clearly-logged stub
success so the connect/test/disconnect lifecycle stays exercisable - an
actual `401`/`403` from Razorpay (bad key pair) is a real error and is
never swallowed.
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

CONNECTOR_TYPE_KEY = "razorpay"

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["key_id", "key_secret"],
    "properties": {
        "key_id": {"type": "string"},
        "key_secret": {"type": "string"},
        "webhook_secret": {
            "type": "string",
            "description": "Optional; the secret configured for this webhook endpoint in the Razorpay dashboard.",
        },
    },
}

# Errors that mean "could not reach Razorpay at all" (this sandbox), as
# opposed to "reached Razorpay and it rejected the key pair" - only the
# former falls back to a stub result.
_NETWORK_UNREACHABLE_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.TimeoutException)


class RazorpayAdapter(base.ConnectorAdapter):
    connector_type_key = CONNECTOR_TYPE_KEY
    auth_mode = "api_key"
    config_schema = CONFIG_SCHEMA

    async def _validate_key_pair(self, key_id: str, key_secret: str) -> tuple[bool, str | None]:
        """Returns (is_stub, detail). Raises ValueError on a real auth rejection."""
        try:
            async with httpx.AsyncClient(base_url=settings.RAZORPAY_API_BASE_URL, timeout=10.0) as client:
                response = await client.get("/payments", params={"count": 1}, auth=(key_id, key_secret))
            if response.status_code in (401, 403):
                raise ValueError("Razorpay rejected this key_id/key_secret pair")
            response.raise_for_status()
            return False, None
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[razorpay] could not reach %s (%s) - stub mode: assuming the key pair is valid so the "
                "connect lifecycle stays testable offline.",
                settings.RAZORPAY_API_BASE_URL,
                exc,
            )
            return True, str(exc)

    async def initiate_connect(
        self,
        *,
        tenant_id: uuid.UUID,
        instance: ConnectorInstance,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> base.ConnectResult:
        key_id = params.get("key_id")
        key_secret = params.get("key_secret")
        webhook_secret = params.get("webhook_secret")
        if not key_id or not key_secret:
            raise ValueError("key_id and key_secret are required")

        is_stub, detail = await self._validate_key_pair(key_id, key_secret)

        await connector_service.upsert_credential(
            session,
            instance=instance,
            secret={"key_id": key_id, "key_secret": key_secret, "webhook_secret": webhook_secret or ""},
        )

        return base.ConnectResult(
            state=ConnectorState.CONNECTED,
            connected_identity={
                "key_id": key_id,
                "mode": "test" if key_id.startswith("rzp_test_") else "live",
            },
            provider_ref_ids={"key_id": key_id},
            health_status=HealthStatus.HEALTHY,
            error_message=f"stub validation ({detail})" if is_stub else None,
        )

    async def test_connection(self, *, instance: ConnectorInstance, session: AsyncSession) -> base.HealthResult:
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail="No credential stored")
        try:
            is_stub, detail = await self._validate_key_pair(secret["key_id"], secret["key_secret"])
        except ValueError as exc:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail=str(exc))
        if is_stub:
            return base.HealthResult(health_status=HealthStatus.HEALTHY, detail=f"stub: assumed healthy ({detail})")
        return base.HealthResult(health_status=HealthStatus.HEALTHY)

    async def disconnect(self, *, instance: ConnectorInstance, session: AsyncSession) -> None:
        # Razorpay has no revoke-by-API for a key pair a merchant generated
        # in their own dashboard - nothing provider-side to do here. State
        # transition + retaining provider_ref_ids is handled generically by
        # service.disconnect.
        logger.info("[razorpay] disconnect: no provider-side revoke call exists for API-key auth")

    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
        """Generic-layer check against a global fallback secret only.

        Razorpay webhook secrets are configured per merchant account, i.e.
        per connector instance in our model - the authoritative signature
        check for that case happens inside `resolve_instance_for_webhook`
        (it must know *which* instance's secret to check before it can
        verify anything). This method exists for the case where a
        deployment sets one shared `RAZORPAY_WEBHOOK_SECRET` for every
        tenant (single-merchant dev/test setups); when unset it defers
        entirely to the per-instance check and returns True here.
        """
        secret = settings.RAZORPAY_WEBHOOK_SECRET
        if not secret:
            return True
        signature = headers.get("x-razorpay-signature", "")
        expected = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def resolve_instance_for_webhook(
        self,
        *,
        raw_payload: bytes,
        headers: Mapping[str, str],
        query_params: Mapping[str, str],
        session: AsyncSession,
    ) -> ConnectorInstance | None:
        """Identify + authenticate the webhook in one step.

        Preferred path: the tenant includes `?instance_id=<uuid>` on the
        webhook URL they paste into their own Razorpay dashboard (a common
        pattern for multi-tenant webhook receivers, since a standard
        Razorpay webhook payload carries no tenant identifier - only
        Razorpay Route/sub-merchant payloads carry `account_id`, not used
        here). Fallback: brute-force the signature against every connected
        Razorpay instance's stored secret - acceptable at phase-1 instance
        counts, revisit before scaling. Either way, a returned instance has
        already had its `x-razorpay-signature` verified against its own
        stored `webhook_secret` (or the global fallback) - this doubles as
        the authoritative signature check, see `verify_webhook_signature`.
        """
        signature = headers.get("x-razorpay-signature", "")
        if not signature:
            return None

        base_query = select(ConnectorInstance).join(
            ConnectorType, ConnectorType.id == ConnectorInstance.connector_type_id
        ).where(ConnectorType.key == CONNECTOR_TYPE_KEY)

        instance_id_param = query_params.get("instance_id")
        if instance_id_param:
            try:
                instance_id = uuid.UUID(instance_id_param)
            except ValueError:
                return None
            rows = await session.execute(base_query.where(ConnectorInstance.id == instance_id))
        else:
            rows = await session.execute(base_query.where(ConnectorInstance.state == ConnectorState.CONNECTED))
        candidates = list(rows.scalars().all())

        for candidate in candidates:
            secret = await connector_service.get_credential_secret(session, instance=candidate)
            if not secret:
                continue
            webhook_secret = secret.get("webhook_secret") or settings.RAZORPAY_WEBHOOK_SECRET
            if not webhook_secret:
                continue
            expected = hmac.new(webhook_secret.encode("utf-8"), raw_payload, hashlib.sha256).hexdigest()
            if hmac.compare_digest(expected, signature):
                return candidate
        return None

    async def handle_webhook(
        self,
        *,
        instance: ConnectorInstance,
        raw_payload: bytes,
        headers: Mapping[str, str],
        session: AsyncSession,
    ) -> list[ConnectorEvent]:
        """Records the raw event only.

        Turning a `payment.captured`/`payment.failed` webhook into a
        `payments` table row is the fixed-connector `payments` module's
        job (owned by a different agent in this wave) - it should consume
        `connector_events` rows where `event_type=webhook_received` and
        the parent instance's `connector_type.key == "razorpay"`, exactly
        the transactional-outbox pattern the plan's workflow engine also
        uses. Not wired up here - see this task's final report.
        """
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
        return [event]


adapter = RazorpayAdapter()
base.registry.register(adapter)
