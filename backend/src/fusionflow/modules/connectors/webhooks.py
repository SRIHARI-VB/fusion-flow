"""Thin inbound webhook receivers: verify signature -> delegate to adapter.

Per the plan's repo layout, a top-level `webhooks/` package is the
long-term home for this (kept isolated as "the most likely first piece to
split out under load"). No such package exists yet in this codebase (Wave
0 has not created it), so this wave's webhook routes live here instead,
scoped to this module's ownership boundary; move them verbatim into a new
top-level `fusionflow/webhooks/` package if/when that convention is
established - nothing here imports anything connector-internal that a move
would break.

Mount point (see this task's final report): `router` here is a second,
independent `APIRouter` - not nested under `router.py`'s `/connectors`
router - because Meta/Razorpay call these URLs directly and unauthenticated
(no bearer token, no tenant context). The plan's API route grouping section
lists `webhooks` alongside `connectors` under `/api/v1/*`, so the
recommended mount is `api_router.include_router(webhooks_router)` in
`api.py` (final paths: `/api/v1/webhooks/whatsapp`,
`/api/v1/webhooks/razorpay`); see the final report for the alternate
top-level mount if that's preferred instead.

Every handler below is provider-agnostic glue - `_dispatch` never branches
on `type_key` beyond picking the right registered adapter. All
provider-specific parsing/verification lives in the adapter, per the
framework's genericity guarantee.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Mapping

from fastapi import APIRouter, HTTPException, Query, Request, Response

from fusionflow.core.deps import SessionDep
from fusionflow.modules.connectors import base
from fusionflow.modules.connectors.config import get_connector_settings

# Imported for their registration side effect (see base.registry) - this
# module can be mounted independently of router.py's authenticated
# `/connectors` router, so it needs its own copy of these imports rather
# than relying on router.py having run first.
from fusionflow.modules.connectors.razorpay import adapter as _razorpay_adapter  # noqa: F401
from fusionflow.modules.connectors.whatsapp import adapter as _whatsapp_adapter  # noqa: F401

logger = logging.getLogger(__name__)
settings = get_connector_settings()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _dispatch(type_key: str, request: Request, session: SessionDep) -> dict[str, object]:
    adapter_impl = base.registry.get_or_none(type_key)
    if adapter_impl is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector type: {type_key!r}")

    raw_payload = await request.body()
    headers: Mapping[str, str] = {k.lower(): v for k, v in request.headers.items()}
    query_params = dict(request.query_params)

    instance = await adapter_impl.resolve_instance_for_webhook(
        raw_payload=raw_payload, headers=headers, query_params=query_params, session=session
    )
    if instance is None:
        # 200 (not 404/401): providers retry aggressively on a non-2xx
        # response, and "we don't recognise this yet" must not trigger a
        # retry storm - log it and move on.
        logger.warning("[webhooks] no matching connector instance for type=%s", type_key)
        return {"received": False}

    if not adapter_impl.verify_webhook_signature(raw_payload=raw_payload, headers=headers):
        logger.warning(
            "[webhooks] signature verification failed for type=%s instance=%s", type_key, instance.id
        )
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    events = await adapter_impl.handle_webhook(
        instance=instance, raw_payload=raw_payload, headers=headers, session=session
    )

    instance.last_webhook_at = datetime.now(timezone.utc)
    await session.commit()
    return {"received": True, "events": len(events)}


@router.post("/whatsapp")
async def whatsapp_webhook(request: Request, session: SessionDep) -> dict[str, object]:
    return await _dispatch("whatsapp", request, session)


@router.get("/whatsapp")
async def whatsapp_webhook_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    """Meta's one-time GET handshake performed when a webhook subscription
    is configured in the App Dashboard - must echo `hub.challenge` back as
    plain text iff `hub.verify_token` matches our configured token."""
    if hub_mode != "subscribe" or hub_verify_token != settings.WHATSAPP_WEBHOOK_VERIFY_TOKEN:
        raise HTTPException(status_code=403, detail="Verification token mismatch")
    return Response(content=hub_challenge, media_type="text/plain")


@router.post("/razorpay")
async def razorpay_webhook(request: Request, session: SessionDep) -> dict[str, object]:
    return await _dispatch("razorpay", request, session)
