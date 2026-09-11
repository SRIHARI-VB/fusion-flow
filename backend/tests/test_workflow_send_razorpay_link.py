"""Offline unit tests for `payments.send_razorpay_link` (composable-builder
redesign, Phase 4) - a plain, non-suspending action that creates a real
Razorpay payment link and sends it over WhatsApp. See that module's
docstring for why there is no bespoke "collect payment" node that also
asks COD-vs-online itself (that's just an ordinary `whatsapp.ask_choice`).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.nodes import _whatsapp_common
from fusionflow.modules.workflows.nodes import payments_send_razorpay_link as node

pytestmark = pytest.mark.asyncio


def _fake_instance(tenant_id: uuid.UUID) -> ConnectorInstance:
    return ConnectorInstance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_type_id=uuid.uuid4(),
        state=ConnectorState.CONNECTED,
        display_name="Test Instance",
        provider_ref_ids={},
    )


def _base_config(razorpay_id: str, whatsapp_id: str) -> dict[str, Any]:
    order_id = str(uuid.uuid4())
    return {
        "razorpay_connector_instance_id": razorpay_id,
        "whatsapp_connector_instance_id": whatsapp_id,
        "to": "{{trigger.from}}",
        "amount": "{{order.total}}",
        "currency": "INR",
        "order_id": order_id,
        "customer_contact": "{{trigger.from}}",
    }, order_id


async def test_execute_creates_link_and_sends_message_with_link_substituted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tenant_id = uuid.uuid4()
    razorpay_instance = _fake_instance(tenant_id)
    whatsapp_instance = _fake_instance(tenant_id)
    sent: list[dict[str, Any]] = []

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance | None:
        if instance_id == razorpay_instance.id:
            return razorpay_instance
        if instance_id == whatsapp_instance.id:
            return whatsapp_instance
        return None

    async def fake_create_payment_link(*, instance, amount, currency, order_id, customer_contact, session):
        assert instance is razorpay_instance
        return {"short_url": "https://rzp.io/abc123", "id": "plink_abc123"}

    async def fake_send_text_message(*, instance, to, body, session) -> None:
        sent.append({"to": to, "body": body})

    monkeypatch.setattr(node.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(node.razorpay_adapter, "create_payment_link", fake_create_payment_link)
    monkeypatch.setattr(node.whatsapp_adapter, "send_text_message", fake_send_text_message)

    config, order_id = _base_config(str(razorpay_instance.id), str(whatsapp_instance.id))
    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="send_link",
        config=config,
        variables={"trigger": {"from": "15551234567"}, "order": {"total": "499.00"}},
    )

    result = await node.SendRazorpayLinkExecutor().execute(context)

    assert isinstance(result, Success)
    assert result.output == {"payment_link": "https://rzp.io/abc123", "provider_ref": "plink_abc123"}
    assert sent == [{"to": "15551234567", "body": "Please complete your payment: https://rzp.io/abc123"}]


async def test_execute_rejects_invalid_razorpay_instance_id() -> None:
    context = ExecutionContext(
        session=None,
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="send_link",
        config={
            "razorpay_connector_instance_id": "not-a-uuid",
            "whatsapp_connector_instance_id": str(uuid.uuid4()),
            "to": "x",
            "amount": "10",
            "order_id": str(uuid.uuid4()),
            "customer_contact": "x",
        },
        variables={},
    )
    result = await node.SendRazorpayLinkExecutor().execute(context)
    assert isinstance(result, Failure)
    assert "razorpay_connector_instance_id" in result.error


async def test_execute_razorpay_instance_not_found_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance | None:
        return None

    monkeypatch.setattr(node.connector_service, "get_instance", fake_get_instance)

    config, _ = _base_config(str(uuid.uuid4()), str(uuid.uuid4()))
    context = ExecutionContext(
        session=None, tenant_id=uuid.uuid4(), run_id=uuid.uuid4(), node_id="send_link", config=config, variables={}
    )
    result = await node.SendRazorpayLinkExecutor().execute(context)
    assert isinstance(result, Failure)
    assert "not found" in result.error


async def test_execute_invalid_amount_is_a_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    razorpay_instance = _fake_instance(tenant_id)

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance | None:
        return razorpay_instance

    monkeypatch.setattr(node.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)

    config, _ = _base_config(str(razorpay_instance.id), str(razorpay_instance.id))
    config["amount"] = "not-a-number"
    context = ExecutionContext(
        session=None, tenant_id=tenant_id, run_id=uuid.uuid4(), node_id="send_link", config=config, variables={}
    )
    result = await node.SendRazorpayLinkExecutor().execute(context)
    assert isinstance(result, Failure)
    assert "amount" in result.error


async def test_execute_wraps_razorpay_value_error_as_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    tenant_id = uuid.uuid4()
    razorpay_instance = _fake_instance(tenant_id)

    async def fake_get_instance(session, *, tenant_id, instance_id) -> ConnectorInstance | None:
        return razorpay_instance

    async def fake_create_payment_link(**kwargs):
        raise ValueError("No credential stored for this Razorpay instance")

    monkeypatch.setattr(node.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(_whatsapp_common.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(node.razorpay_adapter, "create_payment_link", fake_create_payment_link)

    config, _ = _base_config(str(razorpay_instance.id), str(razorpay_instance.id))
    # Literal, non-templated amount/contact - this test only cares about
    # the ValueError-from-the-adapter path, not template resolution, so it
    # must not depend on `{{order.total}}` resolving against an unrelated
    # empty `variables` dict (an unresolved path interpolates to "", which
    # would fail Decimal parsing *before* ever reaching the adapter call).
    config["amount"] = "499.00"
    config["customer_contact"] = "15551234567"
    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="send_link",
        config=config,
        variables={"trigger": {}, "order": {}},
    )
    result = await node.SendRazorpayLinkExecutor().execute(context)
    assert isinstance(result, Failure)
    assert "No credential" in result.error
