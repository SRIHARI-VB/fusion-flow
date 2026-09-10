"""Generic connector lifecycle service.

Every function here is provider-agnostic: the only provider-aware call in
this entire module is `base.registry.get(type_key)`, which returns a
`ConnectorAdapter` and hands control to it. Nothing below ever does
`if type_key == "whatsapp"` or imports a provider package - that is the
framework guarantee the plan calls out explicitly.

Deliberately framework-free (raises `ConnectorError`, not `HTTPException`),
matching `modules/auth/service.py`'s convention - `router.py` maps
`ConnectorError` to an HTTP response.
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fusionflow.core.encryption import CURRENT_KEY_VERSION, decrypt_secret, encrypt_secret, redact_preview
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.connectors import base
from fusionflow.modules.connectors.config import get_connector_settings
from fusionflow.modules.connectors.models import (
    ConnectorCredential,
    ConnectorEvent,
    ConnectorEventType,
    ConnectorInstance,
    ConnectorOAuthState,
    ConnectorState,
    ConnectorType,
    HealthStatus,
)
from fusionflow.modules.connectors.schemas import ConnectorInstanceOut

settings = get_connector_settings()

# States a reconnect (POST /connectors/{type_key}/connect against an
# existing instance) is allowed to start from, besides not_connected.
_RECONNECTABLE_STATES = {
    ConnectorState.NOT_CONNECTED,
    ConnectorState.ERROR,
    ConnectorState.ACTION_REQUIRED,
    ConnectorState.DISCONNECTED,
}


class ConnectorError(Exception):
    """Domain-level connector failure. `status_code` is the HTTP status to emit."""

    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def to_instance_out(instance: ConnectorInstance) -> ConnectorInstanceOut:
    """Instance -> DTO. Reads only the safe-field allowlist columns.

    `instance.connector_type` must already be loaded (see
    `_instance_query`'s `selectinload`) - never lazy-loads here, so this
    stays usable from a webhook-ingestion path that may not have full
    ORM relationship access set up.
    """
    return ConnectorInstanceOut(
        id=instance.id,
        connector_type_id=instance.connector_type_id,
        connector_type_key=instance.connector_type.key,
        connector_type_display_name=instance.connector_type.display_name,
        connector_category=instance.connector_type.category,
        state=instance.state,
        display_name=instance.display_name,
        connected_identity=instance.connected_identity,
        health_status=instance.health_status,
        last_webhook_at=instance.last_webhook_at,
        last_sync_at=instance.last_sync_at,
        last_error_message=instance.last_error_message,
        provider_ref_ids=instance.provider_ref_ids,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        disconnected_at=instance.disconnected_at,
    )


async def list_connector_types(session: AsyncSession) -> list[ConnectorType]:
    rows = await session.execute(select(ConnectorType).order_by(ConnectorType.display_name))
    return list(rows.scalars().all())


async def get_connector_type_by_key(session: AsyncSession, type_key: str) -> ConnectorType | None:
    return (
        await session.execute(select(ConnectorType).where(ConnectorType.key == type_key))
    ).scalar_one_or_none()


def _instance_query():
    return select(ConnectorInstance).options(selectinload(ConnectorInstance.connector_type))


async def list_instances(session: AsyncSession, tenant_id: uuid.UUID) -> list[ConnectorInstance]:
    """All of the tenant's connector instances, across every provider.

    `tenant_id` filtering here is belt-and-suspenders on top of RLS (the
    same defensive pattern `modules/tenancy/router.py` uses for
    `business_id`) - `get_tenant_context` must already have run
    `SET LOCAL` for this query to see any rows at all.
    """
    rows = await session.execute(_instance_query().where(ConnectorInstance.tenant_id == tenant_id))
    return list(rows.scalars().all())


async def get_instance(
    session: AsyncSession, *, tenant_id: uuid.UUID, instance_id: uuid.UUID
) -> ConnectorInstance | None:
    return (
        await session.execute(
            _instance_query().where(
                ConnectorInstance.id == instance_id, ConnectorInstance.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()


async def get_instance_by_id_unscoped(
    session: AsyncSession, instance_id: uuid.UUID
) -> ConnectorInstance | None:
    """Load an instance by id with no tenant filter.

    Used only by the OAuth callback route: the browser redirect back from
    the provider carries no auth token, so the only thing correlating it
    to a tenant is the `state` token (already unguessable, single-use,
    short-lived) resolved via `ConnectorOAuthState`, not a fresh RLS
    check. Never expose this to a route that doesn't already have that
    correlation established.
    """
    return (
        await session.execute(_instance_query().where(ConnectorInstance.id == instance_id))
    ).scalar_one_or_none()


async def _get_or_create_instance(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connector_type: ConnectorType,
    display_name: str | None,
) -> ConnectorInstance:
    """One instance per (tenant, connector_type) in phase 1.

    Reconnecting an existing `error`/`action_required`/`disconnected`
    instance reuses the same row (and its permanently-retained
    `provider_ref_ids`) rather than creating a duplicate.
    """
    existing = (
        await session.execute(
            _instance_query().where(
                ConnectorInstance.tenant_id == tenant_id,
                ConnectorInstance.connector_type_id == connector_type.id,
            )
        )
    ).scalar_one_or_none()

    if existing is not None:
        if existing.state not in _RECONNECTABLE_STATES:
            raise ConnectorError(
                f"{connector_type.key} is already {existing.state.value}; disconnect before reconnecting",
                status_code=409,
            )
        existing.state = ConnectorState.CONNECTING
        existing.last_error_message = None
        existing.disconnected_at = None
        if display_name:
            existing.display_name = display_name
        await session.flush()
        return existing

    instance = ConnectorInstance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_type_id=connector_type.id,
        connector_type=connector_type,
        state=ConnectorState.CONNECTING,
        display_name=display_name or connector_type.display_name,
    )
    session.add(instance)
    await session.flush()
    return instance


async def _record_event(
    session: AsyncSession,
    *,
    instance: ConnectorInstance,
    event_type: ConnectorEventType,
    payload: dict[str, Any],
) -> ConnectorEvent:
    event = ConnectorEvent(
        id=uuid.uuid4(),
        tenant_id=instance.tenant_id,
        connector_instance_id=instance.id,
        event_type=event_type,
        payload=payload,
    )
    session.add(event)
    await session.flush()
    return event


async def connect(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    type_key: str,
    display_name: str | None,
    params: dict[str, Any],
) -> tuple[ConnectorInstance, base.ConnectResult]:
    """Start (api_key: complete) a connection. Commits on success.

    Raises `ConnectorError` (404 unknown/disabled type, 409 already
    connected) before ever calling the adapter; adapter-raised exceptions
    propagate as-is so `router.py` can decide how to surface them (a
    provider validation failure is not the same shape as a framework
    error).
    """
    connector_type = await get_connector_type_by_key(session, type_key)
    if connector_type is None or not connector_type.is_enabled_globally:
        raise ConnectorError(f"Unknown or disabled connector type: {type_key!r}", status_code=404)

    adapter = base.registry.get_or_none(type_key)
    if adapter is None:
        raise ConnectorError(f"No adapter registered for connector type: {type_key!r}", status_code=501)

    instance = await _get_or_create_instance(
        session, tenant_id=tenant_id, connector_type=connector_type, display_name=display_name
    )

    try:
        result = await adapter.initiate_connect(
            tenant_id=tenant_id, instance=instance, params=params, session=session
        )
    except Exception as exc:  # noqa: BLE001 - convert any adapter failure into instance state
        instance.state = ConnectorState.ERROR
        instance.last_error_message = str(exc)
        await _record_event(
            session, instance=instance, event_type=ConnectorEventType.ERROR, payload={"message": str(exc)}
        )
        await commit_and_keep_tenant_context(session)
        raise

    instance.state = result.state
    if result.connected_identity:
        instance.connected_identity = result.connected_identity
    if result.provider_ref_ids:
        instance.provider_ref_ids = {**(instance.provider_ref_ids or {}), **result.provider_ref_ids}
    if result.health_status is not None:
        instance.health_status = result.health_status
    instance.last_error_message = result.error_message
    await session.flush()
    await commit_and_keep_tenant_context(session)
    await session.refresh(instance, attribute_names=["connector_type"])
    return instance, result


async def create_oauth_state(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    instance: ConnectorInstance,
    redirect_context: dict[str, Any] | None = None,
) -> ConnectorOAuthState:
    state = ConnectorOAuthState(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_instance_id=instance.id,
        state_token=secrets.token_urlsafe(32),
        redirect_context=redirect_context or {},
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.OAUTH_STATE_TTL_MINUTES),
    )
    session.add(state)
    await session.flush()
    return state


async def _consume_oauth_state(session: AsyncSession, state_token: str) -> ConnectorOAuthState:
    """Look up + validate a state token. Unscoped by tenant - see callers.

    This is the one place the OAuth callback route is allowed to resolve
    a tenant it doesn't already have a JWT for; it works only because
    `state_token` is a 256-bit unguessable value the tenant's own
    frontend redirect included, not because the query is filtered.
    """
    state = (
        await session.execute(select(ConnectorOAuthState).where(ConnectorOAuthState.state_token == state_token))
    ).scalar_one_or_none()
    if state is None:
        raise ConnectorError("Unknown or already-used OAuth state", status_code=400)
    if state.expires_at <= datetime.now(timezone.utc):
        raise ConnectorError("OAuth state expired; restart the connect flow", status_code=400)
    return state


async def complete_oauth_callback(
    session: AsyncSession, *, type_key: str, state_token: str, code: str
) -> tuple[ConnectorInstance, base.ConnectResult]:
    """Resolve `state` -> tenant/instance, then delegate to the adapter.

    The single generic callback route (plan: `GET
    /connectors/oauth/callback/{type_key}`) calls this and nothing else -
    every provider quirk lives in `adapter.handle_oauth_callback`.
    """
    adapter = base.registry.get_or_none(type_key)
    if adapter is None:
        raise ConnectorError(f"No adapter registered for connector type: {type_key!r}", status_code=501)

    oauth_state = await _consume_oauth_state(session, state_token)
    if oauth_state.connector_instance_id is None:
        raise ConnectorError("OAuth state has no associated connector instance", status_code=400)

    instance = await get_instance_by_id_unscoped(session, oauth_state.connector_instance_id)
    if instance is None or instance.tenant_id != oauth_state.tenant_id:
        raise ConnectorError("Connector instance not found for this OAuth state", status_code=404)

    # Single-use: delete immediately so a replayed callback URL can't
    # complete the flow twice.
    await session.delete(oauth_state)
    await session.flush()

    try:
        result = await adapter.handle_oauth_callback(
            oauth_state=oauth_state, code=code, instance=instance, session=session
        )
    except Exception as exc:  # noqa: BLE001
        instance.state = ConnectorState.ERROR
        instance.last_error_message = str(exc)
        await _record_event(
            session, instance=instance, event_type=ConnectorEventType.ERROR, payload={"message": str(exc)}
        )
        await commit_and_keep_tenant_context(session)
        raise

    instance.state = result.state
    if result.connected_identity:
        instance.connected_identity = result.connected_identity
    if result.provider_ref_ids:
        instance.provider_ref_ids = {**(instance.provider_ref_ids or {}), **result.provider_ref_ids}
    if result.health_status is not None:
        instance.health_status = result.health_status
    instance.last_error_message = result.error_message
    await _record_event(
        session,
        instance=instance,
        event_type=ConnectorEventType.OAUTH_CALLBACK,
        payload={"state": result.state.value},
    )
    await commit_and_keep_tenant_context(session)
    await session.refresh(instance, attribute_names=["connector_type"])
    return instance, result


async def test_connection(
    session: AsyncSession, *, tenant_id: uuid.UUID, instance_id: uuid.UUID
) -> ConnectorInstance:
    instance = await get_instance(session, tenant_id=tenant_id, instance_id=instance_id)
    if instance is None:
        raise ConnectorError("Connector instance not found", status_code=404)

    adapter = base.registry.get(instance.connector_type.key)
    result = await adapter.test_connection(instance=instance, session=session)

    instance.health_status = result.health_status
    instance.last_sync_at = datetime.now(timezone.utc)
    if result.connected_identity:
        instance.connected_identity = {**(instance.connected_identity or {}), **result.connected_identity}
    if result.health_status == HealthStatus.DOWN and instance.state == ConnectorState.CONNECTED:
        instance.state = ConnectorState.ACTION_REQUIRED
        instance.last_error_message = result.detail
    await _record_event(
        session,
        instance=instance,
        event_type=ConnectorEventType.SYNC,
        payload={"health_status": result.health_status.value, "detail": result.detail},
    )
    await commit_and_keep_tenant_context(session)
    await session.refresh(instance, attribute_names=["connector_type"])
    return instance


async def disconnect(
    session: AsyncSession, *, tenant_id: uuid.UUID, instance_id: uuid.UUID
) -> ConnectorInstance:
    """Always behind a confirm dialog on the frontend (plan requirement).

    `provider_ref_ids` are retained permanently for support, per the
    plan's fixed state machine - only `connected_identity`/health are
    left untouched here (a later reconnect refreshes them).
    """
    instance = await get_instance(session, tenant_id=tenant_id, instance_id=instance_id)
    if instance is None:
        raise ConnectorError("Connector instance not found", status_code=404)
    if instance.state == ConnectorState.DISCONNECTED:
        return instance

    adapter = base.registry.get(instance.connector_type.key)
    try:
        await adapter.disconnect(instance=instance, session=session)
    except Exception as exc:  # noqa: BLE001 - best-effort provider cleanup, never blocks disconnect
        await _record_event(
            session,
            instance=instance,
            event_type=ConnectorEventType.ERROR,
            payload={"message": f"provider-side disconnect cleanup failed: {exc}"},
        )

    instance.state = ConnectorState.DISCONNECTED
    instance.disconnected_at = datetime.now(timezone.utc)
    instance.health_status = None
    await commit_and_keep_tenant_context(session)
    await session.refresh(instance, attribute_names=["connector_type"])
    return instance


async def list_events(
    session: AsyncSession, *, tenant_id: uuid.UUID, instance_id: uuid.UUID, limit: int = 100
) -> list[ConnectorEvent]:
    instance = await get_instance(session, tenant_id=tenant_id, instance_id=instance_id)
    if instance is None:
        raise ConnectorError("Connector instance not found", status_code=404)
    rows = await session.execute(
        select(ConnectorEvent)
        .where(ConnectorEvent.connector_instance_id == instance_id)
        .order_by(ConnectorEvent.occurred_at.desc())
        .limit(limit)
    )
    return list(rows.scalars().all())


# --- Credential storage (encrypt/decrypt/redact) -----------------------
#
# The only functions in this module that touch `ConnectorCredential`.
# Adapters call these; routers never do (see schemas.py's module
# docstring for the hard rule this enforces).


async def upsert_credential(
    session: AsyncSession, *, instance: ConnectorInstance, secret: dict[str, Any]
) -> ConnectorCredential:
    """Encrypt `secret` (an arbitrary small JSON-able dict) and store it.

    One active row per instance: rotates in place (stamps `rotated_at`)
    rather than inserting a new row, matching the field shape in the
    plan's data model.
    """
    ciphertext = encrypt_secret(json.dumps(secret, sort_keys=True))
    preview = {k: redact_preview(str(v)) for k, v in secret.items()}

    existing = (
        await session.execute(
            select(ConnectorCredential).where(ConnectorCredential.connector_instance_id == instance.id)
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.ciphertext = ciphertext
        existing.encryption_key_version = CURRENT_KEY_VERSION
        existing.redacted_preview = json.dumps(preview, sort_keys=True)
        existing.rotated_at = datetime.now(timezone.utc)
        await session.flush()
        return existing

    credential = ConnectorCredential(
        id=uuid.uuid4(),
        tenant_id=instance.tenant_id,
        connector_instance_id=instance.id,
        ciphertext=ciphertext,
        encryption_key_version=CURRENT_KEY_VERSION,
        redacted_preview=json.dumps(preview, sort_keys=True),
    )
    session.add(credential)
    await session.flush()
    return credential


async def get_credential_secret(session: AsyncSession, *, instance: ConnectorInstance) -> dict[str, Any] | None:
    """Decrypt and return the stored secret dict, or None if never set.

    Only ever called from adapter code making an outbound provider call
    (plan's secret redaction guarantee) - never from `router.py`.
    """
    credential = (
        await session.execute(
            select(ConnectorCredential).where(ConnectorCredential.connector_instance_id == instance.id)
        )
    ).scalar_one_or_none()
    if credential is None:
        return None
    return json.loads(decrypt_secret(credential.ciphertext, credential.encryption_key_version))
