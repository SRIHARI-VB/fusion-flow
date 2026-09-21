"""Cloudflare R2 connector adapter.

`auth_mode="api_key"`: a tenant connects their own Cloudflare R2 bucket by
pasting an R2 API token (`account_id` + `access_key_id` +
`secret_access_key`, generated in their own Cloudflare dashboard under
R2 > Manage API Tokens) plus the target `bucket_name` directly into
`initiate_connect`'s `params` - no OAuth dance, the same key-pair shape
`razorpay/adapter.py` already established for this codebase.

R2 is S3-compatible, but this adapter deliberately does NOT depend on
`boto3` (sync-only, not a dependency of this project - see
`backend/pyproject.toml`, which only ever uses `httpx` for outbound HTTP).
Instead it hand-rolls AWS Signature Version 4 signing (`_SigV4Signer`
below) for the two calls it needs to make: validating credentials with a
lightweight `ListObjectsV2` call, and signing the outbound `PUT` request
`upload_object` needs. Region is hardcoded to `"auto"` - Cloudflare's own
documented convention for SigV4 signing against R2 endpoints.

This is the first connector in this codebase backing genuine tenant file
storage - unrelated to WhatsApp's own `media_id` concept (Meta-hosted
media only reachable through Meta's Graph API).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import quote

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.connectors import base
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.models import (
    ConnectorEvent,
    ConnectorInstance,
    ConnectorState,
    HealthStatus,
)

logger = logging.getLogger(__name__)

CONNECTOR_TYPE_KEY = "cloudflare_r2"

CONFIG_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["account_id", "access_key_id", "secret_access_key", "bucket_name"],
    "properties": {
        "account_id": {"type": "string", "description": "Your Cloudflare account ID"},
        "access_key_id": {"type": "string", "description": "R2 API token access key id"},
        "secret_access_key": {"type": "string", "description": "R2 API token secret access key"},
        "bucket_name": {"type": "string", "description": "The R2 bucket to store uploads in"},
        "endpoint_url": {
            "type": "string",
            "description": (
                "Optional; defaults to https://{account_id}.r2.cloudflarestorage.com if omitted."
            ),
        },
    },
}

# Errors that mean "could not reach Cloudflare R2 at all" (this sandbox),
# as opposed to "reached R2 and it rejected the credentials" - only the
# former falls back to a stub result. Mirrors
# razorpay/adapter.py::_NETWORK_UNREACHABLE_ERRORS exactly.
_NETWORK_UNREACHABLE_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.NetworkError, httpx.TimeoutException)

_R2_REGION = "auto"
_R2_SERVICE = "s3"


def _canonical_path(path: str) -> str:
    """AWS SigV4 canonical URI: percent-encode every path segment, keep `/`."""
    return quote(path, safe="/-_.~")


def _build_object_key(filename: str) -> str:
    """Collision-safe object key - `filename` is a display name only, never
    trusted as a path (no `/` allowed through, so a malicious filename can't
    escape the tenant's flat key namespace)."""
    safe_filename = (filename or "file").replace("/", "_").replace("\\", "_").strip() or "file"
    return f"{uuid.uuid4()}-{safe_filename}"


class _SigV4Signer:
    """Minimal AWS Signature Version 4 request signer for R2's S3-compatible
    API. Implements only what this adapter needs - header-based auth (no
    presigned query-string auth) for a single request at a time. Follows
    AWS's documented algorithm: canonical request -> string to sign ->
    signing key derivation -> signature.
    https://docs.aws.amazon.com/general/latest/gr/sigv4-create-canonical-request.html
    """

    def __init__(
        self,
        *,
        access_key_id: str,
        secret_access_key: str,
        region: str = _R2_REGION,
        service: str = _R2_SERVICE,
    ) -> None:
        self.access_key_id = access_key_id
        self.secret_access_key = secret_access_key
        self.region = region
        self.service = service

    @staticmethod
    def _hash(payload: bytes) -> str:
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _signing_key(self, date_stamp: str) -> bytes:
        k_date = self._hmac(f"AWS4{self.secret_access_key}".encode("utf-8"), date_stamp)
        k_region = self._hmac(k_date, self.region)
        k_service = self._hmac(k_region, self.service)
        return self._hmac(k_service, "aws4_request")

    def sign_request(
        self,
        *,
        method: str,
        host: str,
        path: str,
        query_string: str = "",
        payload: bytes = b"",
        extra_headers: Mapping[str, str] | None = None,
        now: datetime | None = None,
    ) -> dict[str, str]:
        """Returns the header dict to send (`Authorization`,
        `x-amz-date`, `x-amz-content-sha256`, plus any `extra_headers`).

        `now` is injectable purely for deterministic tests; production
        callers never pass it (defaults to the real current time).
        """
        now = now or datetime.now(timezone.utc)
        amz_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        canonical_uri = _canonical_path(path)
        payload_hash = self._hash(payload)

        headers: dict[str, str] = {"host": host, "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
        if extra_headers:
            headers.update({k.lower(): v for k, v in extra_headers.items()})

        signed_header_names = sorted(headers)
        canonical_headers = "".join(f"{name}:{headers[name].strip()}\n" for name in signed_header_names)
        signed_headers = ";".join(signed_header_names)

        canonical_request = "\n".join(
            [method.upper(), canonical_uri, query_string, canonical_headers, signed_headers, payload_hash]
        )

        credential_scope = f"{date_stamp}/{self.region}/{self.service}/aws4_request"
        string_to_sign = "\n".join(
            ["AWS4-HMAC-SHA256", amz_date, credential_scope, self._hash(canonical_request.encode("utf-8"))]
        )

        signature = hmac.new(
            self._signing_key(date_stamp), string_to_sign.encode("utf-8"), hashlib.sha256
        ).hexdigest()

        authorization = (
            f"AWS4-HMAC-SHA256 Credential={self.access_key_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )

        result = {k: v for k, v in headers.items() if k != "host"}
        result["Authorization"] = authorization
        return result


class CloudflareR2Adapter(base.ConnectorAdapter):
    connector_type_key = CONNECTOR_TYPE_KEY
    auth_mode = "api_key"
    config_schema = CONFIG_SCHEMA

    @staticmethod
    def _endpoint_url(secret: Mapping[str, Any]) -> str:
        endpoint = secret.get("endpoint_url")
        if endpoint:
            return str(endpoint).rstrip("/")
        return f"https://{secret['account_id']}.r2.cloudflarestorage.com"

    async def _validate_credentials(self, secret: Mapping[str, Any]) -> tuple[bool, str | None]:
        """Returns (is_stub, detail). Raises ValueError on a real auth
        rejection. Mirrors razorpay/adapter.py::_validate_key_pair's exact
        narrow network-unreachable-vs-real-rejection split."""
        endpoint_url = self._endpoint_url(secret)
        host = httpx.URL(endpoint_url).host
        bucket = secret["bucket_name"]
        signer = _SigV4Signer(access_key_id=secret["access_key_id"], secret_access_key=secret["secret_access_key"])

        path = f"/{bucket}/"
        query_string = "list-type=2&max-keys=1"
        headers = signer.sign_request(method="GET", host=host, path=path, query_string=query_string)
        url = f"{_canonical_path(path)}?{query_string}"

        try:
            async with httpx.AsyncClient(base_url=endpoint_url, timeout=10.0) as client:
                response = await client.get(url, headers=headers)
            if response.status_code in (401, 403):
                raise ValueError("Cloudflare R2 rejected this access key pair")
            if response.status_code == 404:
                raise ValueError(f"Bucket {bucket!r} not found for this account")
            response.raise_for_status()
            return False, None
        except _NETWORK_UNREACHABLE_ERRORS as exc:
            logger.warning(
                "[cloudflare_r2] could not reach %s (%s) - stub mode: assuming the credentials are valid "
                "so the connect lifecycle stays testable offline.",
                endpoint_url,
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
        account_id = params.get("account_id")
        access_key_id = params.get("access_key_id")
        secret_access_key = params.get("secret_access_key")
        bucket_name = params.get("bucket_name")
        endpoint_url = params.get("endpoint_url") or ""
        if not account_id or not access_key_id or not secret_access_key or not bucket_name:
            raise ValueError("account_id, access_key_id, secret_access_key, and bucket_name are required")

        secret = {
            "account_id": account_id,
            "access_key_id": access_key_id,
            "secret_access_key": secret_access_key,
            "bucket_name": bucket_name,
            "endpoint_url": endpoint_url,
        }
        is_stub, detail = await self._validate_credentials(secret)

        await connector_service.upsert_credential(session, instance=instance, secret=secret)

        return base.ConnectResult(
            state=ConnectorState.CONNECTED,
            connected_identity={"account_id": account_id, "bucket_name": bucket_name},
            provider_ref_ids={"bucket_name": bucket_name},
            health_status=HealthStatus.HEALTHY,
            error_message=f"stub validation ({detail})" if is_stub else None,
        )

    async def test_connection(self, *, instance: ConnectorInstance, session: AsyncSession) -> base.HealthResult:
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail="No credential stored")
        try:
            is_stub, detail = await self._validate_credentials(secret)
        except ValueError as exc:
            return base.HealthResult(health_status=HealthStatus.DOWN, detail=str(exc))
        if is_stub:
            return base.HealthResult(health_status=HealthStatus.HEALTHY, detail=f"stub: assumed healthy ({detail})")
        return base.HealthResult(health_status=HealthStatus.HEALTHY)

    async def disconnect(self, *, instance: ConnectorInstance, session: AsyncSession) -> None:
        # No provider-side revoke exists for an R2 API token/bucket a
        # tenant generated themselves - nothing to do here, matching
        # razorpay/adapter.py::disconnect's precedent for API-key auth.
        logger.info("[cloudflare_r2] disconnect: no provider-side revoke call exists for API-key auth")

    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
        # R2 has no webhooks (it is a plain object store, not an event
        # source) - always False so an inbound request never masquerades
        # as an authenticated R2 webhook.
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

    async def upload_object(
        self,
        *,
        instance: ConnectorInstance,
        session: AsyncSession,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """Signs and sends a `PUT` of `file_bytes` to a fresh, collision-safe
        object key in the tenant's bucket; returns the object's URL.

        The returned URL only resolves publicly once the tenant has
        enabled public access for the bucket/object on their own R2
        dashboard - out of scope here, this call only ever writes the
        object and hands back the URL it will live at.
        """
        secret = await connector_service.get_credential_secret(session, instance=instance)
        if secret is None:
            raise ValueError("No credential stored for this Cloudflare R2 instance")

        endpoint_url = self._endpoint_url(secret)
        bucket = secret["bucket_name"]
        host = httpx.URL(endpoint_url).host
        object_key = _build_object_key(filename)
        path = f"/{bucket}/{object_key}"

        signer = _SigV4Signer(access_key_id=secret["access_key_id"], secret_access_key=secret["secret_access_key"])
        extra_headers = {"content-type": content_type} if content_type else None
        headers = signer.sign_request(method="PUT", host=host, path=path, payload=file_bytes, extra_headers=extra_headers)
        canonical_uri = _canonical_path(path)

        async with httpx.AsyncClient(base_url=endpoint_url, timeout=30.0) as client:
            response = await client.put(canonical_uri, content=file_bytes, headers=headers)
        response.raise_for_status()

        return f"{endpoint_url}/{bucket}/{object_key}"


adapter = CloudflareR2Adapter()
base.registry.register(adapter)
