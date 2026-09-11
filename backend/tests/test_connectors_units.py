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
import uuid
from decimal import Decimal

import httpx
import pytest

from fusionflow.modules.connectors import base
from fusionflow.modules.connectors.config import ConnectorSettings
from fusionflow.modules.connectors.models import ConnectorState, HealthStatus
from fusionflow.modules.connectors.razorpay.adapter import RazorpayAdapter
from fusionflow.modules.connectors.service import ConnectorError, _RECONNECTABLE_STATES
from fusionflow.modules.connectors.whatsapp.adapter import WhatsAppAdapter
from fusionflow.modules.payments.models import Payment

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
# WhatsApp: rich message send methods (stub mode - no real Meta credentials)
# --------------------------------------------------------------------------


class _FakeWhatsAppInstance:
    id = "11111111-1111-1111-1111-111111111111"
    tenant_id = "22222222-2222-2222-2222-222222222222"
    provider_ref_ids = {"waba_id": "waba-1", "phone_number_id": "phone-1"}


async def test_whatsapp_send_media_message_stub_mode_is_a_noop() -> None:
    adapter = WhatsAppAdapter()
    # Ambient module `settings` in this test environment has no
    # WHATSAPP_APP_ID/SECRET configured - whatsapp_configured is False,
    # so this must return cleanly without a session/credential lookup.
    await adapter.send_media_message(
        instance=_FakeWhatsAppInstance(), to="15551234567", media_type="image",
        media_url="https://example.com/pic.jpg", session=None,
    )


async def test_whatsapp_send_media_message_requires_url_or_id() -> None:
    adapter = WhatsAppAdapter()
    with pytest.raises(ValueError, match="media_url or media_id"):
        await adapter.send_media_message(
            instance=_FakeWhatsAppInstance(), to="15551234567", media_type="image", session=None
        )


async def test_whatsapp_send_location_message_stub_mode_is_a_noop() -> None:
    adapter = WhatsAppAdapter()
    await adapter.send_location_message(
        instance=_FakeWhatsAppInstance(), to="15551234567", latitude=1.0, longitude=2.0, session=None
    )


async def test_whatsapp_send_contact_message_stub_mode_is_a_noop() -> None:
    adapter = WhatsAppAdapter()
    await adapter.send_contact_message(
        instance=_FakeWhatsAppInstance(), to="15551234567", contacts=[{"name": "Asha", "phone": "15551230000"}],
        session=None,
    )


async def test_whatsapp_send_interactive_message_stub_mode_is_a_noop() -> None:
    adapter = WhatsAppAdapter()
    await adapter.send_interactive_message(
        instance=_FakeWhatsAppInstance(), to="15551234567", body_text="Pick one",
        interactive_type="button", buttons=[{"id": "yes", "title": "Yes"}], session=None,
    )


async def test_whatsapp_send_template_message_stub_mode_is_a_noop() -> None:
    adapter = WhatsAppAdapter()
    await adapter.send_template_message(
        instance=_FakeWhatsAppInstance(), to="15551234567", template_name="order_confirmation",
        language_code="en_US", body_variables=["Asha", "#1234"], session=None,
    )


async def test_whatsapp_sync_templates_stub_mode_returns_canned_examples() -> None:
    adapter = WhatsAppAdapter()
    templates = await adapter.sync_templates(instance=_FakeWhatsAppInstance(), session=None)
    assert len(templates) >= 1
    assert {"name", "language", "category", "status"} <= set(templates[0])


@pytest.mark.parametrize(
    "action,params",
    [
        ("send_media_message", {"to": "1", "media_type": "image", "media_url": "https://x/y.jpg"}),
        ("send_location_message", {"to": "1", "latitude": 1.0, "longitude": 2.0}),
        ("send_contact_message", {"to": "1", "contacts": [{"name": "A", "phone": "1"}]}),
        ("send_interactive_message", {"to": "1", "body_text": "hi", "interactive_type": "button", "buttons": []}),
        ("send_template_message", {"to": "1", "template_name": "x", "language_code": "en_US"}),
    ],
)
async def test_whatsapp_perform_action_dispatches_every_new_action(action, params) -> None:
    adapter = WhatsAppAdapter()
    result = await adapter.perform_action(
        action=action, params=params, instance=_FakeWhatsAppInstance(), session=None
    )
    assert result["to"] == "1"


async def test_whatsapp_perform_action_unknown_action_raises_not_implemented() -> None:
    adapter = WhatsAppAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.perform_action(
            action="bogus_action", params={}, instance=_FakeWhatsAppInstance(), session=None
        )


# --------------------------------------------------------------------------
# WhatsApp: webhook payload parsing (interactive / media / location /
# contacts / status updates)
# --------------------------------------------------------------------------


def _webhook_body(*, messages: list[dict] | None = None, statuses: list[dict] | None = None, waba_id: str = "waba-1") -> dict:
    value: dict = {}
    if messages is not None:
        value["messages"] = messages
    if statuses is not None:
        value["statuses"] = statuses
    return {"entry": [{"id": waba_id, "changes": [{"value": value}]}]}


def test_extract_inbound_message_parses_interactive_button_reply() -> None:
    body = _webhook_body(
        messages=[
            {
                "from": "15551234567", "id": "wamid.1", "type": "interactive", "timestamp": "1",
                "interactive": {"type": "button_reply", "button_reply": {"id": "yes", "title": "Yes"}},
            }
        ]
    )
    extracted = WhatsAppAdapter._extract_inbound_message(body)
    assert extracted["message_type"] == "interactive"
    assert extracted["interactive"] == {"type": "button_reply", "id": "yes", "title": "Yes"}


def test_extract_inbound_message_parses_interactive_list_reply() -> None:
    body = _webhook_body(
        messages=[
            {
                "from": "1", "id": "wamid.2", "type": "interactive", "timestamp": "1",
                "interactive": {"type": "list_reply", "list_reply": {"id": "row-1", "title": "Support"}},
            }
        ]
    )
    extracted = WhatsAppAdapter._extract_inbound_message(body)
    assert extracted["interactive"] == {"type": "list_reply", "id": "row-1", "title": "Support"}


def test_extract_inbound_message_parses_media() -> None:
    body = _webhook_body(
        messages=[
            {
                "from": "1", "id": "wamid.3", "type": "image", "timestamp": "1",
                "image": {"id": "media-1", "mime_type": "image/jpeg", "caption": "look"},
            }
        ]
    )
    extracted = WhatsAppAdapter._extract_inbound_message(body)
    assert extracted["media"] == {"id": "media-1", "mime_type": "image/jpeg", "caption": "look", "filename": None}


def test_extract_inbound_message_parses_location() -> None:
    body = _webhook_body(
        messages=[
            {"from": "1", "id": "wamid.4", "type": "location", "timestamp": "1",
             "location": {"latitude": 1.0, "longitude": 2.0}}
        ]
    )
    extracted = WhatsAppAdapter._extract_inbound_message(body)
    assert extracted["location"] == {"latitude": 1.0, "longitude": 2.0}


def test_extract_inbound_message_parses_order() -> None:
    body = _webhook_body(
        messages=[
            {
                "from": "1", "id": "wamid.5", "type": "order", "timestamp": "1",
                "order": {
                    "catalog_id": "cat_123",
                    "product_items": [
                        {"product_retailer_id": "p1", "quantity": "2", "item_price": "9.99", "currency": "INR"}
                    ],
                    "text": "please deliver fast",
                },
            }
        ]
    )
    extracted = WhatsAppAdapter._extract_inbound_message(body)
    assert extracted["message_type"] == "order"
    assert extracted["order"] == {
        "catalog_id": "cat_123",
        "product_items": [{"product_retailer_id": "p1", "quantity": "2", "item_price": "9.99", "currency": "INR"}],
        "note": "please deliver fast",
    }


def test_extract_status_update_parses_delivered_status() -> None:
    body = _webhook_body(statuses=[{"id": "wamid.1", "status": "delivered", "recipient_id": "1", "timestamp": "1"}])
    extracted = WhatsAppAdapter._extract_status_update(body)
    assert extracted == {"message_id": "wamid.1", "status": "delivered", "recipient_id": "1", "timestamp": "1", "error": None}


def test_extract_status_update_parses_failed_status_with_error() -> None:
    body = _webhook_body(
        statuses=[{"id": "wamid.1", "status": "failed", "recipient_id": "1", "timestamp": "1",
                   "errors": [{"message": "template not found"}]}]
    )
    extracted = WhatsAppAdapter._extract_status_update(body)
    assert extracted["error"] == "template not found"


def test_extract_status_update_returns_none_when_no_statuses() -> None:
    body = _webhook_body(messages=[{"from": "1", "id": "1", "type": "text", "text": {"body": "hi"}}])
    assert WhatsAppAdapter._extract_status_update(body) is None


async def test_handle_webhook_routes_interactive_reply_to_dedicated_event_type(monkeypatch) -> None:
    published: list[dict] = []

    async def fake_publish_trigger_event(session, **kwargs):
        published.append(kwargs)
        return object()

    async def fake_find_pending_wait(session, **kwargs):
        return None

    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.publish_trigger_event", fake_publish_trigger_event
    )
    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.find_pending_wait", fake_find_pending_wait
    )

    class _FakeSession:
        def add(self, obj: object) -> None:
            pass

        async def flush(self) -> None:
            return None

    adapter = WhatsAppAdapter()
    body = _webhook_body(
        messages=[
            {"from": "1", "id": "wamid.1", "type": "interactive", "timestamp": "1",
             "interactive": {"type": "button_reply", "button_reply": {"id": "yes", "title": "Yes"}}}
        ]
    )
    await adapter.handle_webhook(
        instance=_FakeWhatsAppInstance(), raw_payload=json.dumps(body).encode(), headers={}, session=_FakeSession()
    )

    assert len(published) == 1
    assert published[0]["event_type"] == "whatsapp.interactive_reply_received"
    assert published[0]["dedupe_key"] == "wamid.1"


async def test_handle_webhook_routes_plain_text_to_message_received(monkeypatch) -> None:
    published: list[dict] = []

    async def fake_publish_trigger_event(session, **kwargs):
        published.append(kwargs)
        return object()

    async def fake_find_pending_wait(session, **kwargs):
        return None

    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.publish_trigger_event", fake_publish_trigger_event
    )
    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.find_pending_wait", fake_find_pending_wait
    )

    class _FakeSession:
        def add(self, obj: object) -> None:
            pass

        async def flush(self) -> None:
            return None

    adapter = WhatsAppAdapter()
    body = _webhook_body(messages=[{"from": "1", "id": "wamid.2", "type": "text", "text": {"body": "hi"}}])
    await adapter.handle_webhook(
        instance=_FakeWhatsAppInstance(), raw_payload=json.dumps(body).encode(), headers={}, session=_FakeSession()
    )

    assert len(published) == 1
    assert published[0]["event_type"] == "whatsapp.message_received"


async def test_handle_webhook_resumes_a_pending_wait_instead_of_publishing_a_new_trigger(monkeypatch) -> None:
    """Phase 8 Part A: a reply from a customer with an already-`WAITING`
    run resumes that run (`event_bus.publish_resume_event`) instead of
    firing a normal `whatsapp.message_received` trigger."""
    resumed: list[dict] = []
    published: list[dict] = []
    sentinel_run = object()

    async def fake_find_pending_wait(session, **kwargs):
        return sentinel_run

    async def fake_publish_resume_event(session, **kwargs):
        resumed.append(kwargs)
        return object()

    async def fake_publish_trigger_event(session, **kwargs):
        published.append(kwargs)
        return object()

    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.find_pending_wait", fake_find_pending_wait
    )
    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.publish_resume_event", fake_publish_resume_event
    )
    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.publish_trigger_event", fake_publish_trigger_event
    )

    class _FakeSession:
        def add(self, obj: object) -> None:
            pass

        async def flush(self) -> None:
            return None

    adapter = WhatsAppAdapter()
    body = _webhook_body(messages=[{"from": "1", "id": "wamid.4", "type": "text", "text": {"body": "M"}}])
    await adapter.handle_webhook(
        instance=_FakeWhatsAppInstance(), raw_payload=json.dumps(body).encode(), headers={}, session=_FakeSession()
    )

    assert len(resumed) == 1
    assert resumed[0]["run"] is sentinel_run
    assert resumed[0]["reply_payload"]["text"] == "M"
    assert not published


async def test_handle_webhook_publishes_status_update_event(monkeypatch) -> None:
    published: list[dict] = []

    async def fake_publish_trigger_event(session, **kwargs):
        published.append(kwargs)
        return object()

    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.publish_trigger_event", fake_publish_trigger_event
    )

    class _FakeSession:
        def add(self, obj: object) -> None:
            pass

        async def flush(self) -> None:
            return None

    adapter = WhatsAppAdapter()
    body = _webhook_body(statuses=[{"id": "wamid.3", "status": "read", "recipient_id": "1", "timestamp": "1"}])
    await adapter.handle_webhook(
        instance=_FakeWhatsAppInstance(), raw_payload=json.dumps(body).encode(), headers={}, session=_FakeSession()
    )

    assert len(published) == 1
    assert published[0]["event_type"] == "whatsapp.message_status_updated"
    assert published[0]["dedupe_key"] == "wamid.3:read"


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
# Razorpay: create_payment_link + perform_action + webhook -> payment
# trigger (Phase 8 Part D)
# --------------------------------------------------------------------------


class _FakeRazorpayInstance:
    id = "33333333-3333-3333-3333-333333333333"
    tenant_id = "22222222-2222-2222-2222-222222222222"


async def test_razorpay_create_payment_link_stub_mode_when_network_unreachable(monkeypatch) -> None:
    adapter = RazorpayAdapter()

    async def _fake_get_credential_secret(session, *, instance):
        return {"key_id": "rzp_test_x", "key_secret": "secret"}

    monkeypatch.setattr(
        "fusionflow.modules.connectors.razorpay.adapter.connector_service.get_credential_secret",
        _fake_get_credential_secret,
    )

    def _fake_async_client(*args, **kwargs):
        kwargs.pop("transport", None)
        return _RealAsyncClient(*args, transport=_RaisingTransport(), **kwargs)

    monkeypatch.setattr("fusionflow.modules.connectors.razorpay.adapter.httpx.AsyncClient", _fake_async_client)

    result = await adapter.create_payment_link(
        instance=_FakeRazorpayInstance(),
        amount=Decimal("499.00"),
        currency="INR",
        order_id=uuid.uuid4(),
        customer_contact="+911234567890",
        session=None,
    )
    assert result["short_url"] == "https://rzp.io/stub-link"
    assert result["id"].startswith("stub-plink-")


async def test_razorpay_create_payment_link_raises_when_no_credential_stored(monkeypatch) -> None:
    adapter = RazorpayAdapter()

    async def _fake_get_credential_secret(session, *, instance):
        return None

    monkeypatch.setattr(
        "fusionflow.modules.connectors.razorpay.adapter.connector_service.get_credential_secret",
        _fake_get_credential_secret,
    )

    with pytest.raises(ValueError, match="No credential"):
        await adapter.create_payment_link(
            instance=_FakeRazorpayInstance(),
            amount=Decimal("499.00"),
            currency="INR",
            order_id=uuid.uuid4(),
            customer_contact="+911234567890",
            session=None,
        )


async def test_razorpay_perform_action_dispatches_create_payment_link(monkeypatch) -> None:
    adapter = RazorpayAdapter()
    captured: dict = {}

    async def _fake_create_payment_link(*, instance, amount, currency, order_id, customer_contact, session):
        captured.update(amount=amount, currency=currency, order_id=order_id, customer_contact=customer_contact)
        return {"short_url": "https://rzp.io/x", "id": "plink_1"}

    monkeypatch.setattr(adapter, "create_payment_link", _fake_create_payment_link)

    order_id = uuid.uuid4()
    result = await adapter.perform_action(
        action="create_payment_link",
        params={
            "amount": "499.00",
            "currency": "INR",
            "order_id": str(order_id),
            "customer_contact": "+911234567890",
        },
        instance=_FakeRazorpayInstance(),
        session=None,
    )

    assert result == {"short_url": "https://rzp.io/x", "id": "plink_1"}
    assert captured["amount"] == Decimal("499.00")
    assert captured["order_id"] == order_id
    assert captured["customer_contact"] == "+911234567890"


@pytest.mark.parametrize("missing_key", ["amount", "currency", "order_id", "customer_contact"])
async def test_razorpay_perform_action_create_payment_link_requires_all_params(missing_key) -> None:
    adapter = RazorpayAdapter()
    params = {
        "amount": "499.00", "currency": "INR", "order_id": str(uuid.uuid4()), "customer_contact": "+911234567890",
    }
    params.pop(missing_key)
    with pytest.raises(ValueError, match="requires non-empty"):
        await adapter.perform_action(
            action="create_payment_link", params=params, instance=_FakeRazorpayInstance(), session=None
        )


async def test_razorpay_perform_action_create_payment_link_rejects_invalid_order_id() -> None:
    adapter = RazorpayAdapter()
    params = {
        "amount": "499.00", "currency": "INR", "order_id": "not-a-uuid", "customer_contact": "+911234567890",
    }
    with pytest.raises(ValueError, match="not a valid UUID"):
        await adapter.perform_action(
            action="create_payment_link", params=params, instance=_FakeRazorpayInstance(), session=None
        )


async def test_razorpay_perform_action_create_payment_link_rejects_invalid_amount() -> None:
    adapter = RazorpayAdapter()
    params = {
        "amount": "not-a-number", "currency": "INR", "order_id": str(uuid.uuid4()),
        "customer_contact": "+911234567890",
    }
    with pytest.raises(ValueError, match="not a valid decimal"):
        await adapter.perform_action(
            action="create_payment_link", params=params, instance=_FakeRazorpayInstance(), session=None
        )


async def test_razorpay_perform_action_unknown_action_raises_not_implemented() -> None:
    adapter = RazorpayAdapter()
    with pytest.raises(NotImplementedError):
        await adapter.perform_action(action="bogus_action", params={}, instance=_FakeRazorpayInstance(), session=None)


class _FakeConnectorEventSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, obj: object) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None


def _razorpay_payment_webhook_body(
    *, event: str, payment_id: str, status: str, amount: int = 49900, currency: str = "INR",
    order_id: str | None = None, customer_id: str | None = None,
) -> dict:
    notes: dict = {}
    if order_id:
        notes["internal_order_id"] = order_id
    if customer_id:
        notes["internal_customer_id"] = customer_id
    return {
        "event": event,
        "payload": {
            "payment": {
                "entity": {"id": payment_id, "status": status, "amount": amount, "currency": currency, "notes": notes}
            }
        },
    }


def _fake_upsert_payment_from_provider(monkeypatch) -> None:
    """Stands in for `payments_service.upsert_payment_from_provider` -
    returns a real (unpersisted) `Payment` row, same shape the real
    function returns, so `handle_webhook` has an id to publish."""

    async def _fake(session, **kwargs):
        return Payment(
            id=uuid.uuid4(),
            tenant_id=kwargs["tenant_id"],
            order_id=kwargs.get("order_id"),
            customer_id=kwargs.get("customer_id"),
            connector_instance_id=kwargs["connector_instance_id"],
            provider_ref=kwargs["provider_ref"],
            amount=kwargs["amount"],
            currency=kwargs["currency"],
            status=kwargs["status"],
        )

    monkeypatch.setattr(
        "fusionflow.modules.connectors.razorpay.adapter.payments_service.upsert_payment_from_provider", _fake
    )


async def test_razorpay_handle_webhook_publishes_payment_captured_trigger(monkeypatch) -> None:
    published: list[dict] = []

    async def _fake_publish_trigger_event(session, **kwargs):
        published.append(kwargs)
        return object()

    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.publish_trigger_event", _fake_publish_trigger_event
    )
    _fake_upsert_payment_from_provider(monkeypatch)

    adapter = RazorpayAdapter()
    order_id = str(uuid.uuid4())
    body = _razorpay_payment_webhook_body(event="payment.captured", payment_id="pay_1", status="captured", order_id=order_id)
    await adapter.handle_webhook(
        instance=_FakeRazorpayInstance(), raw_payload=json.dumps(body).encode(), headers={},
        session=_FakeConnectorEventSession(),
    )

    assert len(published) == 1
    assert published[0]["event_type"] == "payment.captured"
    assert published[0]["dedupe_key"] == "pay_1"
    assert published[0]["payload"]["order_id"] == order_id
    assert published[0]["payload"]["status"] == "captured"


async def test_razorpay_handle_webhook_publishes_payment_failed_trigger(monkeypatch) -> None:
    published: list[dict] = []

    async def _fake_publish_trigger_event(session, **kwargs):
        published.append(kwargs)
        return object()

    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.publish_trigger_event", _fake_publish_trigger_event
    )
    _fake_upsert_payment_from_provider(monkeypatch)

    adapter = RazorpayAdapter()
    body = _razorpay_payment_webhook_body(event="payment.failed", payment_id="pay_2", status="failed")
    await adapter.handle_webhook(
        instance=_FakeRazorpayInstance(), raw_payload=json.dumps(body).encode(), headers={},
        session=_FakeConnectorEventSession(),
    )

    assert len(published) == 1
    assert published[0]["event_type"] == "payment.failed"
    assert published[0]["dedupe_key"] == "pay_2"


async def test_razorpay_handle_webhook_skips_publish_for_pending_authorized_status(monkeypatch) -> None:
    published: list[dict] = []

    async def _fake_publish_trigger_event(session, **kwargs):
        published.append(kwargs)
        return object()

    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.publish_trigger_event", _fake_publish_trigger_event
    )
    _fake_upsert_payment_from_provider(monkeypatch)

    adapter = RazorpayAdapter()
    body = _razorpay_payment_webhook_body(event="payment.authorized", payment_id="pay_3", status="authorized")
    await adapter.handle_webhook(
        instance=_FakeRazorpayInstance(), raw_payload=json.dumps(body).encode(), headers={},
        session=_FakeConnectorEventSession(),
    )

    assert published == []


async def test_razorpay_handle_webhook_redelivered_webhook_does_not_double_publish(monkeypatch) -> None:
    """A redelivered webhook (same Razorpay payment id => same `provider_ref`
    => same `dedupe_key`) must not fire the workflow twice. The real
    dedupe-by-`(tenant_id, dedupe_key)` uniqueness lives inside
    `event_bus.publish_trigger_event` itself (see its docstring) and needs a
    real Postgres session to exercise for real - no DB-backed connector
    fixture exists in this suite yet (see this file's module docstring), so
    this in-memory fake reproduces that exact documented contract to prove
    `handle_webhook` always passes the same `dedupe_key` on redelivery,
    which is what makes the real dedupe effective."""
    inbox: dict[str, dict] = {}

    async def _fake_publish_trigger_event(session, *, tenant_id, event_type, payload, connector_instance_id=None, dedupe_key=None):
        if dedupe_key is not None and dedupe_key in inbox:
            return inbox[dedupe_key]
        row = {"event_type": event_type, "payload": payload, "dedupe_key": dedupe_key}
        if dedupe_key is not None:
            inbox[dedupe_key] = row
        return row

    monkeypatch.setattr(
        "fusionflow.modules.workflows.engine.event_bus.publish_trigger_event", _fake_publish_trigger_event
    )
    _fake_upsert_payment_from_provider(monkeypatch)

    adapter = RazorpayAdapter()
    body = _razorpay_payment_webhook_body(event="payment.captured", payment_id="pay_redelivered", status="captured")
    raw_payload = json.dumps(body).encode()

    await adapter.handle_webhook(
        instance=_FakeRazorpayInstance(), raw_payload=raw_payload, headers={}, session=_FakeConnectorEventSession()
    )
    await adapter.handle_webhook(
        instance=_FakeRazorpayInstance(), raw_payload=raw_payload, headers={}, session=_FakeConnectorEventSession()
    )

    assert len(inbox) == 1


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
