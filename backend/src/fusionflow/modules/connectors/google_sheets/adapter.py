"""Google Sheets connector adapter.

`auth_mode="oauth"`: unlike WhatsApp/Razorpay/Cloudflare R2 (all
`auth_mode="api_key"`, tenant pastes a key pair), this connector goes
through the shared Google OAuth2 helper (`connectors/google/oauth.py`) -
the tenant clicks "Connect with Google", is redirected to Google's consent
screen, and lands back on `GET /connectors/oauth/callback/google_sheets`
with an authorization code this adapter exchanges for tokens. There is no
per-tenant credential form (`config_schema` below is deliberately empty) -
nothing about *this* connect step is Sheets-specific; only the requested
`SCOPES` differ from `google_calendar`/`gmail`/`google_meet`, which share
the exact same OAuth app/client id (see `config.py`'s
`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` and `google/oauth.py`'s module
docstring).

Scope: `https://www.googleapis.com/auth/spreadsheets` - full read/write
access to Sheets values. There is no narrower "values-only" scope Google
publishes that still allows both `read_rows` and `append_rows`; the
read-only `.../auth/spreadsheets.readonly` scope would block
`append_rows` entirely, so the read/write scope is requested even though
some tenants may only ever use this connector for reads.

Deliberate "no single spreadsheet per instance" design: unlike, say, a
Cloudflare R2 instance (which owns exactly one bucket, chosen at connect
time) or a WhatsApp instance (which owns exactly one phone number), a
connected Google Sheets instance does not point at any particular
spreadsheet. A tenant's business may read/append rows across many
different spreadsheets from many different workflows, and Google's OAuth
consent for this scope already grants access to every spreadsheet the
authorizing user can reach - there is no meaningful "pick one spreadsheet
now" step to insert into `initiate_connect`. Instead, every capability
below (`read_rows`, `append_rows`, and their `perform_action` dispatch)
takes its own `spreadsheet_id` per call, supplied by the workflow node
config that invokes it - the connector instance is purely an OAuth
credential holder, not a binding to one sheet.

Stub-on-network-unreachable convention: token exchange/refresh/revoke and
userinfo lookups all go through `connectors/google/oauth.py`, which
already implements this codebase's standard stub fallback (see its module
docstring) - this adapter does not reimplement any of that. The two real
Sheets API calls this adapter makes directly (`read_rows`/`append_rows`)
do not get their own stub fallback: unlike a health-check or a "does this
credential still work" call, there is no sensible canned value to fake for
an arbitrary tenant-supplied `spreadsheet_id`/`range_a1`, so a network or
API failure here is left to propagate as a genuine error.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Mapping
from urllib.parse import quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.connectors import base
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.config import get_connector_settings
from fusionflow.modules.connectors.google import oauth as google_oauth
from fusionflow.modules.connectors.models import (
    ConnectorEvent,
    ConnectorInstance,
    ConnectorOAuthState,
    ConnectorState,
    HealthStatus,
)

logger = logging.getLogger(__name__)
settings = get_connector_settings()

CONNECTOR_TYPE_KEY = "google_sheets"

# Full read/write access to spreadsheet values - see module docstring for
# why no narrower scope covers both read_rows and append_rows.
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# No user-entered params: the tenant clicks a button and is redirected to
# Google - see module docstring.
CONFIG_SCHEMA: dict[str, Any] = {"type": "object", "properties": {}, "required": []}


class GoogleSheetsAdapter(base.ConnectorAdapter):
    connector_type_key = CONNECTOR_TYPE_KEY
    auth_mode = "oauth"
    config_schema = CONFIG_SCHEMA

    async def initiate_connect(
        self,
        *,
        tenant_id: uuid.UUID,
        instance: ConnectorInstance,
        params: dict[str, Any],
        session: AsyncSession,
    ) -> base.ConnectResult:
        """Starts the OAuth dance - no credential exists yet, so nothing is
        stored here (that happens in `handle_oauth_callback` once Google's
        redirect hands back an authorization code)."""
        oauth_state = await connector_service.create_oauth_state(session, tenant_id=tenant_id, instance=instance)
        return base.ConnectResult(
            state=ConnectorState.CONNECTING,
            redirect_url=google_oauth.build_authorize_url(
                type_key=CONNECTOR_TYPE_KEY, scopes=SCOPES, state=oauth_state.state_token
            ),
        )

    async def handle_oauth_callback(
        self,
        *,
        oauth_state: ConnectorOAuthState,
        code: str,
        instance: ConnectorInstance,
        session: AsyncSession,
    ) -> base.ConnectResult:
        result = await google_oauth.exchange_code_for_tokens(type_key=CONNECTOR_TYPE_KEY, code=code)
        _is_stub_identity, identity = await google_oauth.fetch_userinfo(access_token=result.access_token)

        await connector_service.upsert_credential(
            session,
            instance=instance,
            secret={
                "access_token": result.access_token,
                "refresh_token": result.refresh_token,
                "expires_at": result.expires_at,
                "scope": result.scope,
                "token_type": result.token_type,
            },
        )

        return base.ConnectResult(
            state=ConnectorState.CONNECTED,
            connected_identity={"email": identity.get("email"), "name": identity.get("name")},
            health_status=HealthStatus.HEALTHY,
            error_message=f"stub token exchange ({result.detail})" if result.is_stub else None,
        )

    async def test_connection(self, *, instance: ConnectorInstance, session: AsyncSession) -> base.HealthResult:
        """The Sheets API has no cheap "list all spreadsheets"/health-check
        endpoint that doesn't require naming a specific `spreadsheet_id` -
        and this connector instance deliberately doesn't own one (see
        module docstring: every call names its own spreadsheet). So the
        health signal used here is simply "is the stored OAuth credential
        still valid/refreshable" - `get_valid_access_token` already does a
        refresh if the access token is near expiry, and raises if Google
        has actually revoked the underlying grant. That is the strongest
        check available without picking an arbitrary spreadsheet to probe.
        """
        try:
            await google_oauth.get_valid_access_token(session, instance=instance)
        except (RuntimeError, ValueError) as exc:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail=str(exc))
        return base.HealthResult(health_status=HealthStatus.HEALTHY)

    async def disconnect(self, *, instance: ConnectorInstance, session: AsyncSession) -> None:
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return
        await google_oauth.revoke_token(token=secret.get("refresh_token") or secret.get("access_token"))

    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
        # Google Sheets has no inbound webhooks - always False, mirrors
        # cloudflare_r2/adapter.py exactly.
        return False

    async def resolve_instance_for_webhook(
        self,
        *,
        raw_payload: bytes,
        headers: Mapping[str, str],
        query_params: Mapping[str, str],
        session: AsyncSession,
    ) -> ConnectorInstance | None:
        return None

    async def handle_webhook(
        self,
        *,
        instance: ConnectorInstance,
        raw_payload: bytes,
        headers: Mapping[str, str],
        session: AsyncSession,
    ) -> list[ConnectorEvent]:
        return []

    async def read_rows(
        self, instance: ConnectorInstance, session: AsyncSession, *, spreadsheet_id: str, range_a1: str
    ) -> list[list[Any]]:
        """`range_a1` is an A1-notation range string, e.g. `"Sheet1!A1:D20"`."""
        access_token = await google_oauth.get_valid_access_token(session, instance=instance)
        encoded_range = quote(range_a1, safe="")
        async with httpx.AsyncClient(base_url=settings.GOOGLE_SHEETS_API_BASE_URL, timeout=15.0) as client:
            response = await client.get(
                f"/spreadsheets/{spreadsheet_id}/values/{encoded_range}",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
        return response.json().get("values", [])

    async def append_rows(
        self,
        instance: ConnectorInstance,
        session: AsyncSession,
        *,
        spreadsheet_id: str,
        range_a1: str,
        rows: list[list[Any]],
    ) -> dict[str, Any]:
        access_token = await google_oauth.get_valid_access_token(session, instance=instance)
        encoded_range = quote(range_a1, safe="")
        async with httpx.AsyncClient(base_url=settings.GOOGLE_SHEETS_API_BASE_URL, timeout=15.0) as client:
            response = await client.post(
                f"/spreadsheets/{spreadsheet_id}/values/{encoded_range}:append",
                params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
                headers={"Authorization": f"Bearer {access_token}"},
                json={"values": rows},
            )
            response.raise_for_status()
        return response.json()

    async def perform_action(
        self, *, action: str, params: dict[str, Any], instance: ConnectorInstance, session: AsyncSession
    ) -> dict[str, Any]:
        """Dispatch for the generic `connector.action` workflow node type -
        mirrors `whatsapp/adapter.py::perform_action`'s style exactly.
        `spreadsheet_id`/`range_a1` are always required (there is no "the"
        spreadsheet for this connector instance - see module docstring);
        `rows` is additionally required for `append_rows`."""
        if action == "read_rows":
            spreadsheet_id = params.get("spreadsheet_id")
            range_a1 = params.get("range_a1")
            if not spreadsheet_id or not range_a1:
                raise ValueError("read_rows requires non-empty 'spreadsheet_id' and 'range_a1' params")
            values = await self.read_rows(instance, session, spreadsheet_id=spreadsheet_id, range_a1=range_a1)
            return {"values": values}
        if action == "append_rows":
            spreadsheet_id = params.get("spreadsheet_id")
            range_a1 = params.get("range_a1")
            rows = params.get("rows")
            if not spreadsheet_id or not range_a1:
                raise ValueError("append_rows requires non-empty 'spreadsheet_id' and 'range_a1' params")
            if not rows:
                raise ValueError("append_rows requires a non-empty 'rows' param")
            return await self.append_rows(
                instance, session, spreadsheet_id=spreadsheet_id, range_a1=range_a1, rows=rows
            )
        raise NotImplementedError(f"{self.connector_type_key} does not support action {action!r}")


adapter = GoogleSheetsAdapter()
base.registry.register(adapter)
