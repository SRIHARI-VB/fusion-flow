"""Offline unit tests for the Cloudflare R2 connector adapter (see
`test_connectors_units.py`'s module docstring for why these don't need
Postgres) plus the `POST /connectors/{instance_id}/media` upload route.

Covers: the hand-rolled SigV4 signing helper, `initiate_connect`'s
network-unreachable stub fallback (mirroring
`test_razorpay_validate_key_pair_falls_back_to_stub_when_network_unreachable`),
`upload_object`'s outbound PUT shape, and the upload endpoint with a
mocked adapter/instance lookup.
"""

from __future__ import annotations

import datetime as dt
import uuid

import httpx
import pytest

from fusionflow.modules.connectors import base
from fusionflow.modules.connectors.cloudflare_r2.adapter import (
    CloudflareR2Adapter,
    _SigV4Signer,
    _build_object_key,
    _canonical_path,
)
from fusionflow.modules.connectors.models import ConnectorState

# --------------------------------------------------------------------------
# _SigV4Signer
# --------------------------------------------------------------------------

_FIXED_NOW = dt.datetime(2024, 1, 5, 12, 30, 0, tzinfo=dt.timezone.utc)


def test_sigv4_sign_request_produces_well_formed_authorization_header() -> None:
    signer = _SigV4Signer(access_key_id="AKIDEXAMPLE", secret_access_key="secret")
    headers = signer.sign_request(
        method="GET",
        host="example-account.r2.cloudflarestorage.com",
        path="/my-bucket/",
        query_string="list-type=2&max-keys=1",
        payload=b"",
        now=_FIXED_NOW,
    )

    assert set(headers) == {"x-amz-content-sha256", "x-amz-date", "Authorization"}
    assert headers["x-amz-date"] == "20240105T123000Z"
    auth = headers["Authorization"]
    assert auth.startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20240105/auto/s3/aws4_request, ")
    assert "SignedHeaders=host;x-amz-content-sha256;x-amz-date" in auth
    assert "Signature=" in auth
    # Signature is a lowercase hex sha256 digest (64 chars).
    signature = auth.split("Signature=")[1]
    assert len(signature) == 64
    int(signature, 16)  # raises ValueError if not valid hex


def test_sigv4_sign_request_is_deterministic_for_fixed_inputs() -> None:
    signer = _SigV4Signer(access_key_id="AKIDEXAMPLE", secret_access_key="secret")
    kwargs = dict(method="PUT", host="h.example.com", path="/bucket/key.txt", payload=b"hello world", now=_FIXED_NOW)
    first = signer.sign_request(**kwargs)
    second = signer.sign_request(**kwargs)
    assert first == second


def test_sigv4_sign_request_changes_signature_when_payload_changes() -> None:
    signer = _SigV4Signer(access_key_id="AKIDEXAMPLE", secret_access_key="secret")
    headers_a = signer.sign_request(method="PUT", host="h.example.com", path="/b/k", payload=b"a", now=_FIXED_NOW)
    headers_b = signer.sign_request(method="PUT", host="h.example.com", path="/b/k", payload=b"b", now=_FIXED_NOW)
    assert headers_a["Authorization"] != headers_b["Authorization"]
    assert headers_a["x-amz-content-sha256"] != headers_b["x-amz-content-sha256"]


def test_sigv4_sign_request_includes_extra_headers_signed() -> None:
    signer = _SigV4Signer(access_key_id="AKIDEXAMPLE", secret_access_key="secret")
    headers = signer.sign_request(
        method="PUT",
        host="h.example.com",
        path="/b/k",
        payload=b"data",
        extra_headers={"Content-Type": "image/png"},
        now=_FIXED_NOW,
    )
    assert headers["content-type"] == "image/png"
    assert "SignedHeaders=content-type;host;x-amz-content-sha256;x-amz-date" in headers["Authorization"]


def test_canonical_path_encodes_special_characters_but_keeps_slashes() -> None:
    assert _canonical_path("/my bucket/a file.png") == "/my%20bucket/a%20file.png"
    assert _canonical_path("/bucket/key") == "/bucket/key"


def test_build_object_key_is_collision_safe_and_strips_path_separators() -> None:
    key_a = _build_object_key("a/b/../c.png")
    key_b = _build_object_key("a/b/../c.png")
    assert key_a != key_b  # each call gets a fresh uuid prefix
    assert "/" not in key_a
    assert key_a.endswith("a_b_.._c.png")


def test_build_object_key_falls_back_to_file_for_empty_name() -> None:
    key = _build_object_key("")
    assert key.endswith("-file")


# --------------------------------------------------------------------------
# initiate_connect / test_connection: network-unreachable stub fallback
# --------------------------------------------------------------------------

_RealAsyncClient = httpx.AsyncClient


class _RaisingTransport(httpx.AsyncBaseTransport):
    """Simulates "no network reachable" for httpx.AsyncClient calls."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated: no network in this sandbox", request=request)


class _FixedResponseTransport(httpx.AsyncBaseTransport):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code=self.status_code, request=request)


_SAMPLE_SECRET = {
    "account_id": "acct123",
    "access_key_id": "AKIDEXAMPLE",
    "secret_access_key": "secret",
    "bucket_name": "my-bucket",
    "endpoint_url": "",
}


async def test_validate_credentials_falls_back_to_stub_when_network_unreachable(monkeypatch) -> None:
    adapter = CloudflareR2Adapter()

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_RaisingTransport(), **kwargs)

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.httpx.AsyncClient", _fake_async_client
    )

    is_stub, detail = await adapter._validate_credentials(_SAMPLE_SECRET)
    assert is_stub is True
    assert detail is not None


async def test_validate_credentials_rejects_real_401(monkeypatch) -> None:
    adapter = CloudflareR2Adapter()

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_FixedResponseTransport(401), **kwargs)

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.httpx.AsyncClient", _fake_async_client
    )

    with pytest.raises(ValueError, match="rejected"):
        await adapter._validate_credentials(_SAMPLE_SECRET)


async def test_validate_credentials_rejects_missing_bucket_404(monkeypatch) -> None:
    adapter = CloudflareR2Adapter()

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_FixedResponseTransport(404), **kwargs)

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.httpx.AsyncClient", _fake_async_client
    )

    with pytest.raises(ValueError, match="not found"):
        await adapter._validate_credentials(_SAMPLE_SECRET)


async def test_validate_credentials_accepts_real_200(monkeypatch) -> None:
    adapter = CloudflareR2Adapter()

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_FixedResponseTransport(200), **kwargs)

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.httpx.AsyncClient", _fake_async_client
    )

    is_stub, detail = await adapter._validate_credentials(_SAMPLE_SECRET)
    assert is_stub is False
    assert detail is None


class _FakeR2Instance:
    id = "11111111-1111-1111-1111-111111111111"
    tenant_id = "22222222-2222-2222-2222-222222222222"


async def test_initiate_connect_requires_all_fields() -> None:
    adapter = CloudflareR2Adapter()
    with pytest.raises(ValueError, match="required"):
        await adapter.initiate_connect(
            tenant_id=uuid.uuid4(),
            instance=_FakeR2Instance(),
            params={"account_id": "a"},
            session=None,
        )


async def test_initiate_connect_stores_credential_and_returns_connected_result(monkeypatch) -> None:
    adapter = CloudflareR2Adapter()
    stored: dict = {}

    async def _fake_upsert_credential(session, *, instance, secret):
        stored.update(secret)
        return object()

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.connector_service.upsert_credential",
        _fake_upsert_credential,
    )

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_RaisingTransport(), **kwargs)

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.httpx.AsyncClient", _fake_async_client
    )

    result = await adapter.initiate_connect(
        tenant_id=uuid.uuid4(),
        instance=_FakeR2Instance(),
        params={
            "account_id": "acct123",
            "access_key_id": "AKIDEXAMPLE",
            "secret_access_key": "secret",
            "bucket_name": "my-bucket",
        },
        session=None,
    )

    assert result.state == ConnectorState.CONNECTED
    assert result.connected_identity == {"account_id": "acct123", "bucket_name": "my-bucket"}
    assert result.provider_ref_ids == {"bucket_name": "my-bucket"}
    assert result.error_message is not None  # stub-mode detail, network unreachable in this sandbox
    assert stored["bucket_name"] == "my-bucket"


async def test_disconnect_never_raises() -> None:
    adapter = CloudflareR2Adapter()
    await adapter.disconnect(instance=_FakeR2Instance(), session=None)


def test_verify_webhook_signature_always_false() -> None:
    adapter = CloudflareR2Adapter()
    assert adapter.verify_webhook_signature(raw_payload=b"{}", headers={}) is False


async def test_resolve_instance_for_webhook_always_none() -> None:
    adapter = CloudflareR2Adapter()
    assert await adapter.resolve_instance_for_webhook(
        raw_payload=b"{}", headers={}, query_params={}, session=None
    ) is None


async def test_handle_webhook_returns_no_events() -> None:
    adapter = CloudflareR2Adapter()
    events = await adapter.handle_webhook(instance=_FakeR2Instance(), raw_payload=b"{}", headers={}, session=None)
    assert events == []


def test_registry_has_cloudflare_r2_registered() -> None:
    """Importing router.py registers it - same pattern as the whatsapp/razorpay check."""
    from fusionflow.modules.connectors import router as _router  # noqa: F401

    assert "cloudflare_r2" in base.registry.registered_keys()
    r2_adapter = base.registry.get("cloudflare_r2")
    assert r2_adapter.auth_mode == "api_key"


# --------------------------------------------------------------------------
# upload_object: httpx call shape
# --------------------------------------------------------------------------


async def test_upload_object_raises_when_no_credential_stored(monkeypatch) -> None:
    adapter = CloudflareR2Adapter()

    async def _fake_get_credential_secret(session, *, instance):
        return None

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.connector_service.get_credential_secret",
        _fake_get_credential_secret,
    )

    with pytest.raises(ValueError, match="No credential"):
        await adapter.upload_object(
            instance=_FakeR2Instance(), session=None, file_bytes=b"x", filename="a.png", content_type="image/png"
        )


async def test_upload_object_puts_bytes_and_returns_url(monkeypatch) -> None:
    adapter = CloudflareR2Adapter()

    async def _fake_get_credential_secret(session, *, instance):
        return dict(_SAMPLE_SECRET)

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.connector_service.get_credential_secret",
        _fake_get_credential_secret,
    )

    captured: dict = {}

    class _RecordingTransport(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            captured["method"] = request.method
            captured["url"] = str(request.url)
            captured["headers"] = dict(request.headers)
            captured["content"] = request.content
            return httpx.Response(status_code=200, request=request)

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_RecordingTransport(), **kwargs)

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.httpx.AsyncClient", _fake_async_client
    )

    url = await adapter.upload_object(
        instance=_FakeR2Instance(), session=None, file_bytes=b"file-bytes", filename="pic.png", content_type="image/png"
    )

    assert captured["method"] == "PUT"
    assert captured["content"] == b"file-bytes"
    assert "authorization" in captured["headers"]
    assert captured["headers"]["content-type"] == "image/png"
    assert "/my-bucket/" in captured["url"]
    assert url.startswith("https://acct123.r2.cloudflarestorage.com/my-bucket/")
    assert url.endswith("-pic.png")


async def test_upload_object_raises_on_http_error(monkeypatch) -> None:
    adapter = CloudflareR2Adapter()

    async def _fake_get_credential_secret(session, *, instance):
        return dict(_SAMPLE_SECRET)

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.connector_service.get_credential_secret",
        _fake_get_credential_secret,
    )

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_FixedResponseTransport(403), **kwargs)

    monkeypatch.setattr(
        "fusionflow.modules.connectors.cloudflare_r2.adapter.httpx.AsyncClient", _fake_async_client
    )

    with pytest.raises(httpx.HTTPStatusError):
        await adapter.upload_object(
            instance=_FakeR2Instance(), session=None, file_bytes=b"x", filename="a.png", content_type="image/png"
        )


# --------------------------------------------------------------------------
# POST /connectors/{instance_id}/media - endpoint, mocked service/adapter
# --------------------------------------------------------------------------


async def test_upload_media_endpoint_returns_url_from_adapter(monkeypatch) -> None:
    """Exercises the route function directly with dependency overrides on
    the ASGI app (no Postgres/JWT round trip - this repo has no existing
    HTTP-level connector-endpoint test fixture to mirror, see this task's
    final report), monkeypatching the connector-service lookup and the
    adapter's `upload_object` the same way the adapter-level tests above
    mock `httpx.AsyncClient`."""
    import io

    from fusionflow.core.deps import TenantContext, get_tenant_context
    from fusionflow.db.session import get_db_session
    from fusionflow.main import app
    from fusionflow.modules.connectors import router as connectors_router
    from fusionflow.modules.tenancy.models import MembershipRole

    class _FakeConnectorType:
        key = "cloudflare_r2"

    class _FakeInstance:
        id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        connector_type = _FakeConnectorType()

    async def _fake_get_instance(session, *, tenant_id, instance_id):
        return _FakeInstance()

    async def _fake_upload_object(*, instance, session, file_bytes, filename, content_type):
        assert file_bytes == b"hello-bytes"
        return "https://acct.r2.cloudflarestorage.com/bucket/fake-key-hello.txt"

    monkeypatch.setattr(connectors_router.connector_service, "get_instance", _fake_get_instance)
    monkeypatch.setattr(connectors_router._cloudflare_r2_adapter.adapter, "upload_object", _fake_upload_object)

    class _FakeUser:
        id = uuid.uuid4()

    async def _fake_session_dep():
        yield object()

    async def _fake_tenant_context_dep():
        return TenantContext(tenant_id=uuid.uuid4(), role=MembershipRole.OWNER, user=_FakeUser())

    app.dependency_overrides[get_db_session] = _fake_session_dep
    app.dependency_overrides[get_tenant_context] = _fake_tenant_context_dep
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/connectors/{uuid.uuid4()}/media",
                files={"file": ("hello.txt", io.BytesIO(b"hello-bytes"), "text/plain")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"url": "https://acct.r2.cloudflarestorage.com/bucket/fake-key-hello.txt"}


async def test_upload_media_endpoint_404s_for_wrong_connector_type(monkeypatch) -> None:
    from fusionflow.core.deps import TenantContext, get_tenant_context
    from fusionflow.db.session import get_db_session
    from fusionflow.main import app
    from fusionflow.modules.connectors import router as connectors_router
    from fusionflow.modules.tenancy.models import MembershipRole

    class _FakeConnectorType:
        key = "razorpay"

    class _FakeInstance:
        id = uuid.uuid4()
        tenant_id = uuid.uuid4()
        connector_type = _FakeConnectorType()

    async def _fake_get_instance(session, *, tenant_id, instance_id):
        return _FakeInstance()

    monkeypatch.setattr(connectors_router.connector_service, "get_instance", _fake_get_instance)

    class _FakeUser:
        id = uuid.uuid4()

    async def _fake_session_dep():
        yield object()

    async def _fake_tenant_context_dep():
        return TenantContext(tenant_id=uuid.uuid4(), role=MembershipRole.OWNER, user=_FakeUser())

    app.dependency_overrides[get_db_session] = _fake_session_dep
    app.dependency_overrides[get_tenant_context] = _fake_tenant_context_dep
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                f"/api/v1/connectors/{uuid.uuid4()}/media",
                files={"file": ("hello.txt", b"data", "text/plain")},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
