"""Offline unit tests for the connector framework (M3/M4).

None of these need Postgres - they exercise the parts of the connector
framework that don't touch the database: the adapter registry, webhook
signature verification (Meta's `X-Hub-Signature-256`, Razorpay's
`X-Razorpay-Signature`), and each adapter's network-unreachable stub
fallback. DB-backed paths (`service.py`'s persistence, credential
encrypt/decrypt round-trips against a real `ConnectorInstance` row) need
Postgres with this wave's tables migrated, which does not exist yet in
this environment - see this task's final report.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import httpx
import pytest

from fusionflow.modules.connectors import base
from fusionflow.modules.connectors.config import ConnectorSettings
from fusionflow.modules.connectors.models import ConnectorState, HealthStatus
from fusionflow.modules.connectors.razorpay.adapter import RazorpayAdapter
from fusionflow.modules.connectors.service import ConnectorError, _RECONNECTABLE_STATES
from fusionflow.modules.connectors.whatsapp.adapter import WhatsAppAdapter

# --------------------------------------------------------------------------
# base.ConnectorRegistry
# --------------------------------------------------------------------------


def test_registry_registers_and_looks_up_by_key() -> None:
    registry = base.ConnectorRegistry()
    adapter = WhatsAppAdapter()
    registry.register(adapter)

    assert registry.get("whatsapp") is adapter
    assert registry.get_or_none("whatsapp") is adapter
    assert registry.get_or_none("nope") is None
    assert "whatsapp" in registry.registered_keys()


def test_registry_raises_lookup_error_for_unknown_key() -> None:
    registry = base.ConnectorRegistry()
    with pytest.raises(LookupError):
        registry.get("does-not-exist")


def test_module_level_registry_has_both_phase_1_adapters() -> None:
    """Importing router.py registers both - see its module docstring."""
    from fusionflow.modules.connectors import router as _router  # noqa: F401

    assert set(base.registry.registered_keys()) >= {"whatsapp", "razorpay"}
    whatsapp_adapter = base.registry.get("whatsapp")
    razorpay_adapter = base.registry.get("razorpay")
    assert whatsapp_adapter.auth_mode == "oauth"
    assert razorpay_adapter.auth_mode == "api_key"


# --------------------------------------------------------------------------
# WhatsApp: webhook signature verification + stub-mode connect
# --------------------------------------------------------------------------


def _hub_signature(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def test_whatsapp_verify_webhook_signature_accepts_valid_hmac(monkeypatch) -> None:
    adapter = WhatsAppAdapter()
    monkeypatch.setattr(
        "fusionflow.modules.connectors.whatsapp.adapter.settings",
        ConnectorSettings(WHATSAPP_WEBHOOK_APP_SECRET="app-secret"),
    )
    payload = b'{"object":"whatsapp_business_account"}'
    headers = {"x-hub-signature-256": _hub_signature("app-secret", payload)}
    assert adapter.verify_webhook_signature(raw_payload=payload, headers=headers) is True


def test_whatsapp_verify_webhook_signature_rejects_tampered_body(monkeypatch) -> None:
    adapter = WhatsAppAdapter()
    monkeypatch.setattr(
        "fusionflow.modules.connectors.whatsapp.adapter.settings",
        ConnectorSettings(WHATSAPP_WEBHOOK_APP_SECRET="app-secret"),
    )
    payload = b'{"object":"whatsapp_business_account"}'
    headers = {"x-hub-signature-256": _hub_signature("app-secret", payload)}
    assert adapter.verify_webhook_signature(raw_payload=payload + b"tampered", headers=headers) is False


def test_whatsapp_verify_webhook_signature_rejects_missing_header(monkeypatch) -> None:
    adapter = WhatsAppAdapter()
    monkeypatch.setattr(
        "fusionflow.modules.connectors.whatsapp.adapter.settings",
        ConnectorSettings(WHATSAPP_WEBHOOK_APP_SECRET="app-secret"),
    )
    assert adapter.verify_webhook_signature(raw_payload=b"{}", headers={}) is False


def test_whatsapp_verify_webhook_signature_dev_fallback_when_unconfigured(monkeypatch) -> None:
    """No app secret configured at all - dev-only accept-unverified path."""
    adapter = WhatsAppAdapter()
    monkeypatch.setattr(
        "fusionflow.modules.connectors.whatsapp.adapter.settings",
        ConnectorSettings(WHATSAPP_WEBHOOK_APP_SECRET=None, WHATSAPP_APP_SECRET=None),
    )
    assert adapter.verify_webhook_signature(raw_payload=b"{}", headers={}) is True


async def test_whatsapp_stub_connected_result_shape() -> None:
    """Stub-mode fallback (no WHATSAPP_APP_ID/SECRET) returns a fully-formed,
    safe-allowlist ConnectResult - exercised directly since the full
    initiate_connect path needs a DB session for the OAuth state row."""
    adapter = WhatsAppAdapter()
    result = await adapter._stub_connected_result()

    assert result.state == ConnectorState.CONNECTED
    assert result.health_status == HealthStatus.HEALTHY
    assert "waba_id" in result.connected_identity
    assert result.provider_ref_ids["waba_id"] == result.connected_identity["waba_id"]
    # Never leaks anything secret-shaped - just the display allowlist.
    assert set(result.connected_identity) <= {"display_phone_number", "verified_name", "waba_id"}


async def test_whatsapp_handle_webhook_parses_json_payload() -> None:
    class _FakeInstance:
        id = "11111111-1111-1111-1111-111111111111"
        tenant_id = "22222222-2222-2222-2222-222222222222"

    class _FakeSession:
        def __init__(self) -> None:
            self.added: list[object] = []

        def add(self, obj: object) -> None:
            self.added.append(obj)

        async def flush(self) -> None:
            return None

    adapter = WhatsAppAdapter()
    session = _FakeSession()
    payload = json.dumps({"object": "whatsapp_business_account", "entry": [{"id": "waba-1"}]}).encode()

    events = await adapter.handle_webhook(
        instance=_FakeInstance(), raw_payload=payload, headers={}, session=session
    )

    assert len(events) == 1
    assert events[0].payload["entry"][0]["id"] == "waba-1"
    assert session.added == events


# --------------------------------------------------------------------------
# Razorpay: webhook signature verification + network-unreachable stub
# --------------------------------------------------------------------------


def _razorpay_signature(secret: str, payload: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def test_razorpay_verify_webhook_signature_defers_when_no_global_secret(monkeypatch) -> None:
    adapter = RazorpayAdapter()
    monkeypatch.setattr(
        "fusionflow.modules.connectors.razorpay.adapter.settings",
        ConnectorSettings(RAZORPAY_WEBHOOK_SECRET=None),
    )
    # No global secret configured -> generic layer defers to the
    # per-instance check in resolve_instance_for_webhook, so this always
    # returns True regardless of the (wrong) signature below.
    assert adapter.verify_webhook_signature(raw_payload=b"{}", headers={"x-razorpay-signature": "bogus"}) is True


def test_razorpay_verify_webhook_signature_checks_global_secret_when_set(monkeypatch) -> None:
    adapter = RazorpayAdapter()
    monkeypatch.setattr(
        "fusionflow.modules.connectors.razorpay.adapter.settings",
        ConnectorSettings(RAZORPAY_WEBHOOK_SECRET="whsec_test"),
    )
    payload = b'{"event":"payment.captured"}'
    good_headers = {"x-razorpay-signature": _razorpay_signature("whsec_test", payload)}
    bad_headers = {"x-razorpay-signature": "0" * 64}

    assert adapter.verify_webhook_signature(raw_payload=payload, headers=good_headers) is True
    assert adapter.verify_webhook_signature(raw_payload=payload, headers=bad_headers) is False


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


async def test_razorpay_validate_key_pair_falls_back_to_stub_when_network_unreachable(monkeypatch) -> None:
    adapter = RazorpayAdapter()

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_RaisingTransport(), **kwargs)

    monkeypatch.setattr("fusionflow.modules.connectors.razorpay.adapter.httpx.AsyncClient", _fake_async_client)

    is_stub, detail = await adapter._validate_key_pair("rzp_test_x", "secret")
    assert is_stub is True
    assert detail is not None


async def test_razorpay_validate_key_pair_rejects_real_401(monkeypatch) -> None:
    adapter = RazorpayAdapter()

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_FixedResponseTransport(401), **kwargs)

    monkeypatch.setattr("fusionflow.modules.connectors.razorpay.adapter.httpx.AsyncClient", _fake_async_client)

    with pytest.raises(ValueError, match="rejected"):
        await adapter._validate_key_pair("rzp_test_x", "wrong-secret")


async def test_razorpay_validate_key_pair_accepts_real_200(monkeypatch) -> None:
    adapter = RazorpayAdapter()

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_FixedResponseTransport(200), **kwargs)

    monkeypatch.setattr("fusionflow.modules.connectors.razorpay.adapter.httpx.AsyncClient", _fake_async_client)

    is_stub, detail = await adapter._validate_key_pair("rzp_test_x", "correct-secret")
    assert is_stub is False
    assert detail is None


# --------------------------------------------------------------------------
# service.py: pure/offline pieces
# --------------------------------------------------------------------------


def test_connector_error_carries_status_code() -> None:
    err = ConnectorError("nope", status_code=409)
    assert err.detail == "nope"
    assert err.status_code == 409


def test_reconnectable_states_excludes_connecting_and_connected() -> None:
    """A live/in-flight connection must never be silently reconnected over."""
    assert ConnectorState.CONNECTING not in _RECONNECTABLE_STATES
    assert ConnectorState.CONNECTED not in _RECONNECTABLE_STATES
    assert ConnectorState.ERROR in _RECONNECTABLE_STATES
    assert ConnectorState.ACTION_REQUIRED in _RECONNECTABLE_STATES
    assert ConnectorState.DISCONNECTED in _RECONNECTABLE_STATES
    assert ConnectorState.NOT_CONNECTED in _RECONNECTABLE_STATES
