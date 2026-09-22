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

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, Response
from sqlalchemy import select

from fusionflow.config import get_settings
from fusionflow.core.deps import SessionDep
from fusionflow.db.session import commit_and_keep_tenant_context, set_tenant_context, unscoped_session_factory
from fusionflow.modules.connectors import base
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.config import get_connector_settings
from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorType

# Imported for their registration side effect (see base.registry) - this
# module can be mounted independently of router.py's authenticated
# `/connectors` router, so it needs its own copy of these imports rather
# than relying on router.py having run first.
from fusionflow.modules.connectors.facebook import adapter as _facebook_adapter  # noqa: F401
from fusionflow.modules.connectors.instagram import adapter as _instagram_adapter  # noqa: F401
from fusionflow.modules.connectors.razorpay import adapter as _razorpay_adapter  # noqa: F401
from fusionflow.modules.connectors.telegram import adapter as _telegram_adapter  # noqa: F401
from fusionflow.modules.connectors.whatsapp import adapter as _whatsapp_adapter  # noqa: F401

logger = logging.getLogger(__name__)
settings = get_connector_settings()

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _dispatch(
    type_key: str, request: Request, session: SessionDep, background_tasks: BackgroundTasks
) -> dict[str, object]:
    adapter_impl = base.registry.get_or_none(type_key)
    if adapter_impl is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector type: {type_key!r}")

    raw_payload = await request.body()
    headers: Mapping[str, str] = {k.lower(): v for k, v in request.headers.items()}
    query_params = dict(request.query_params)

    # Resolution runs on `unscoped_session_factory`, not the request's
    # normal (RLS-restricted) `session`: at this point nobody has set
    # `app.current_tenant_id` yet (webhooks carry no bearer token, so
    # there's no tenant to derive one from), and `resolve_instance_for_webhook`
    # has to read `connector_instances` (tenant-scoped) to figure out
    # *which* tenant this is - a chicken-and-egg problem confirmed live:
    # that lookup returns zero rows under RLS with no context set, even
    # for a row that demonstrably exists. The instance object returned
    # here is only used to read `.tenant_id`/`.id`; it is intentionally
    # discarded once the unscoped session closes rather than mutated -
    # see the re-fetch below.
    async with unscoped_session_factory() as unscoped_session:
        candidate = await adapter_impl.resolve_instance_for_webhook(
            raw_payload=raw_payload, headers=headers, query_params=query_params, session=unscoped_session
        )
        if candidate is None:
            # 200 (not 404/401): providers retry aggressively on a non-2xx
            # response, and "we don't recognise this yet" must not trigger a
            # retry storm - log it and move on.
            logger.warning("[webhooks] no matching connector instance for type=%s", type_key)
            return {"received": False}
        tenant_id, instance_id = candidate.tenant_id, candidate.id

    if not adapter_impl.verify_webhook_signature(raw_payload=raw_payload, headers=headers):
        logger.warning(
            "[webhooks] signature verification failed for type=%s instance=%s", type_key, instance_id
        )
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Now that the tenant is known (established above via a signature- and
    # lookup-authenticated token, not caller-supplied input), set it on the
    # request's normal session and re-fetch the instance through that -
    # every write from here on (ConnectorEvent, any Payment row, this
    # instance's own last_webhook_at) goes through the properly
    # RLS-scoped session, never the unscoped one.
    await set_tenant_context(session, tenant_id)
    instance = await connector_service.get_instance(session, tenant_id=tenant_id, instance_id=instance_id)
    if instance is None:
        logger.warning("[webhooks] resolved instance %s vanished on re-fetch", instance_id)
        return {"received": False}

    events = await adapter_impl.handle_webhook(
        instance=instance, raw_payload=raw_payload, headers=headers, session=session
    )

    instance.last_webhook_at = datetime.now(timezone.utc)
    await commit_and_keep_tenant_context(session)

    if get_settings().is_serverless:
        # No persistent process to run `outbox_poller`'s background loop
        # in (see `Settings.is_serverless`'s docstring) - dispatch this
        # tenant's just-written trigger-inbox row(s) after this response
        # is sent, via FastAPI's `BackgroundTasks`, instead of leaving
        # them to a poller that would never actually run.
        #
        # Deliberately NOT awaited inline here (an earlier version did):
        # dispatching a run can mean a real outbound API call to the
        # provider (e.g. a comment-automation or button-menu reply),
        # which can push this handler's total response time close to
        # Meta's webhook retry threshold - confirmed live, Meta redelivers
        # the identical event (same payload/id) roughly every 20s when a
        # response is slow, and a redelivered trigger with no dedupe key
        # (or one that's merely rare, not impossible) fires its own extra
        # run - a single button tap producing several replies. Responding
        # to Meta immediately and dispatching afterward, in the same
        # request's background-task phase (FastAPI keeps `session`'s
        # dependency alive until this finishes), removes the main reason
        # Meta would need to retry in the first place.
        #
        # Deferred import: `workflows.engine.outbox_poller` pulls in the
        # `workflows` package, which imports every built-in node
        # (including the connector adapters, for registration) -
        # importing it at module level here would risk exactly the
        # circular import `handle_webhook`'s own deferred `event_bus`/
        # `inbox.service` imports already dodge, one layer further out.
        from fusionflow.modules.workflows.engine.outbox_poller import process_pending_now

        background_tasks.add_task(process_pending_now, session, tenant_id)

    return {"received": True, "events": len(events)}


@router.post("/whatsapp")
async def whatsapp_webhook(
    request: Request, session: SessionDep, background_tasks: BackgroundTasks
) -> dict[str, object]:
    return await _dispatch("whatsapp", request, session, background_tasks)


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
async def razorpay_webhook(
    request: Request, session: SessionDep, background_tasks: BackgroundTasks
) -> dict[str, object]:
    return await _dispatch("razorpay", request, session, background_tasks)


@router.post("/instagram")
async def instagram_webhook(
    request: Request, session: SessionDep, background_tasks: BackgroundTasks
) -> dict[str, object]:
    return await _dispatch("instagram", request, session, background_tasks)


async def _instagram_verify_token_matches_any_instance(token: str) -> bool:
    """Check `token` against every connected Instagram instance's own
    stored `webhook_verify_token` - see `instagram/adapter.py`'s module
    docstring for why a per-tenant value is honored here, unlike
    WhatsApp's single global token (Meta's GET handshake carries no
    tenant identifier, so the only way to support a per-tenant value at
    all is to check the inbound token against every candidate). Runs on
    `unscoped_session_factory` (no tenant context exists yet during this
    handshake, same chicken-and-egg problem `_dispatch`'s instance
    resolution has) - read-only, never mutates anything, and the number
    of connected Instagram instances is small enough that a full scan per
    handshake call (a rare, one-time-per-app-setup event) is not a
    concern.
    """
    async with unscoped_session_factory() as session:
        rows = await session.execute(
            select(ConnectorInstance)
            .join(ConnectorType, ConnectorType.id == ConnectorInstance.connector_type_id)
            .where(ConnectorType.key == "instagram")
        )
        for instance in rows.scalars().all():
            secret = await connector_service.get_credential_secret(session, instance=instance)
            if secret and secret.get("webhook_verify_token") and secret["webhook_verify_token"] == token:
                return True
    return False


@router.get("/instagram")
async def instagram_webhook_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    """Meta's one-time GET handshake performed when a webhook subscription
    is configured in the App Dashboard - must echo `hub.challenge` back as
    plain text iff `hub.verify_token` matches either the platform's own
    default (`INSTAGRAM_WEBHOOK_VERIFY_TOKEN`) or some connected tenant's
    own per-instance token (see `_instagram_verify_token_matches_any_instance`).
    """
    if hub_mode != "subscribe":
        raise HTTPException(status_code=403, detail="Verification token mismatch")
    if hub_verify_token == settings.INSTAGRAM_WEBHOOK_VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    if await _instagram_verify_token_matches_any_instance(hub_verify_token):
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/facebook")
async def facebook_webhook(
    request: Request, session: SessionDep, background_tasks: BackgroundTasks
) -> dict[str, object]:
    return await _dispatch("facebook", request, session, background_tasks)


async def _facebook_verify_token_matches_any_instance(token: str) -> bool:
    """Same per-instance-then-global handshake check as
    `_instagram_verify_token_matches_any_instance` - see that function's
    docstring for the full rationale (Meta's GET handshake carries no
    tenant identifier, so a per-tenant `webhook_verify_token` can only be
    supported by checking every connected instance)."""
    async with unscoped_session_factory() as session:
        rows = await session.execute(
            select(ConnectorInstance)
            .join(ConnectorType, ConnectorType.id == ConnectorInstance.connector_type_id)
            .where(ConnectorType.key == "facebook")
        )
        for instance in rows.scalars().all():
            secret = await connector_service.get_credential_secret(session, instance=instance)
            if secret and secret.get("webhook_verify_token") and secret["webhook_verify_token"] == token:
                return True
    return False


@router.get("/facebook")
async def facebook_webhook_verify(
    hub_mode: str = Query(alias="hub.mode"),
    hub_verify_token: str = Query(alias="hub.verify_token"),
    hub_challenge: str = Query(alias="hub.challenge"),
) -> Response:
    """Meta's one-time GET handshake - see `instagram_webhook_verify`'s
    identical shape/docstring."""
    if hub_mode != "subscribe":
        raise HTTPException(status_code=403, detail="Verification token mismatch")
    if hub_verify_token == settings.FACEBOOK_WEBHOOK_VERIFY_TOKEN:
        return Response(content=hub_challenge, media_type="text/plain")
    if await _facebook_verify_token_matches_any_instance(hub_verify_token):
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/telegram")
async def telegram_webhook(
    request: Request, session: SessionDep, background_tasks: BackgroundTasks
) -> dict[str, object]:
    """No matching `GET /webhooks/telegram` handshake route - unlike Meta's
    providers, Telegram has no GET-based verification step at all; this
    adapter self-registers its own webhook (with a `secret_token` and a
    `?instance_id=` query param baked into the URL) via `setWebhook` inside
    `initiate_connect` - see `telegram/adapter.py`'s module docstring."""
    return await _dispatch("telegram", request, session, background_tasks)
