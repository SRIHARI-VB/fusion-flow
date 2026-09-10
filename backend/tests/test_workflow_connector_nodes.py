"""Offline unit tests for the 4 connector/fixed-connector-backed workflow
node executors added to close plan item 3 ("Workflow node set for the
sample scenario"): `whatsapp.message_received`, `order.created`,
`send_whatsapp_message`, `create_ticket`.

Same "no Postgres required" philosophy as `test_workflows_engine.py` — the
two action nodes' DB-touching dependencies (`connector_service.get_instance`,
`whatsapp_adapter.send_text_message`, `tickets_service.create_ticket`) are
monkeypatched rather than exercised against a real session.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from pydantic import ValidationError

from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState
from fusionflow.modules.tickets.models import Ticket, TicketStatus
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.nodes import create_ticket as create_ticket_node
from fusionflow.modules.workflows.nodes import order_created as order_created_node
from fusionflow.modules.workflows.nodes import send_whatsapp_message as send_whatsapp_node
from fusionflow.modules.workflows.nodes import whatsapp_message_received as whatsapp_trigger_node

pytestmark = pytest.mark.asyncio


def _context(config: dict[str, Any], variables: dict[str, Any], session: Any = None) -> ExecutionContext:
    return ExecutionContext(
        session=session,
        tenant_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_id="node-under-test",
        config=config,
        variables=variables,
    )


# --------------------------------------------------------------------------
# Triggers: whatsapp.message_received / order.created
# --------------------------------------------------------------------------


async def test_whatsapp_message_received_config_accepts_empty_and_optional_description() -> None:
    executor = whatsapp_trigger_node.WhatsAppMessageReceivedExecutor()
    executor.validate_config({})
    executor.validate_config({"description": "keyword trigger"})
    with pytest.raises(ValidationError):
        executor.validate_config({"description": "x" * 500})


async def test_whatsapp_message_received_execute_echoes_trigger_payload() -> None:
    executor = whatsapp_trigger_node.WhatsAppMessageReceivedExecutor()
    payload = {"from": "15551234567", "text": "refund please", "message_id": "wamid.abc"}
    context = _context({}, {"trigger": payload})

    result = await executor.execute(context)

    assert isinstance(result, Success)
    assert result.output == payload


async def test_order_created_config_accepts_empty() -> None:
    executor = order_created_node.OrderCreatedExecutor()
    executor.validate_config({})
    executor.validate_config({"description": "new order"})


async def test_order_created_execute_echoes_trigger_payload() -> None:
    executor = order_created_node.OrderCreatedExecutor()
    payload = {"order_id": str(uuid.uuid4()), "status": "pending"}
    context = _context({}, {"trigger": payload})

    result = await executor.execute(context)

    assert isinstance(result, Success)
    assert result.output == payload


# --------------------------------------------------------------------------
# Action: send_whatsapp_message
# --------------------------------------------------------------------------


def _fake_connector_instance(tenant_id: uuid.UUID) -> ConnectorInstance:
    return ConnectorInstance(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_type_id=uuid.uuid4(),
        state=ConnectorState.CONNECTED,
        display_name="Test WhatsApp",
        provider_ref_ids={"phone_number_id": "stub-phone-1"},
    )


async def test_send_whatsapp_message_config_requires_fields() -> None:
    executor = send_whatsapp_node.SendWhatsAppMessageExecutor()
    executor.validate_config(
        {"connector_instance_id": str(uuid.uuid4()), "to": "{{trigger.from}}", "body": "hi"}
    )
    with pytest.raises(ValidationError):
        executor.validate_config({"to": "x", "body": "y"})  # missing connector_instance_id


async def test_send_whatsapp_message_interpolates_and_calls_adapter(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = send_whatsapp_node.SendWhatsAppMessageExecutor()
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)

    calls: list[dict[str, Any]] = []

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        assert instance_id == instance.id
        return instance

    async def fake_send_text_message(*, instance: ConnectorInstance, to: str, body: str, session: Any) -> None:
        calls.append({"to": to, "body": body})

    monkeypatch.setattr(send_whatsapp_node.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_whatsapp_node.whatsapp_adapter, "send_text_message", fake_send_text_message)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="send",
        config={
            "connector_instance_id": str(instance.id),
            "to": "{{trigger.from}}",
            "body": "Thanks {{trigger.from}}, we got your message: {{trigger.text}}",
        },
        variables={"trigger": {"from": "15551234567", "text": "refund please"}},
    )

    result = await executor.execute(context)

    assert isinstance(result, Success)
    assert calls == [
        {"to": "15551234567", "body": "Thanks 15551234567, we got your message: refund please"}
    ]


async def test_send_whatsapp_message_propagates_adapter_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """An adapter exception is deliberately left un-caught (unlike a plain
    config/lookup error, which stays a `Failure`) so run_loop.py's
    retry-with-backoff (this node is `retryable = True`) actually gets a
    chance to retry it instead of the node swallowing it into a single,
    permanent `Failure` before retry logic ever sees it."""
    executor = send_whatsapp_node.SendWhatsAppMessageExecutor()
    assert executor.retryable is True
    assert executor.max_retries == 2
    tenant_id = uuid.uuid4()
    instance = _fake_connector_instance(tenant_id)

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> ConnectorInstance:
        return instance

    async def fake_send_text_message(**kwargs: Any) -> None:
        raise RuntimeError("no credential stored")

    monkeypatch.setattr(send_whatsapp_node.connector_service, "get_instance", fake_get_instance)
    monkeypatch.setattr(send_whatsapp_node.whatsapp_adapter, "send_text_message", fake_send_text_message)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="send",
        config={"connector_instance_id": str(instance.id), "to": "123", "body": "hi"},
        variables={},
    )

    with pytest.raises(RuntimeError, match="no credential stored"):
        await executor.execute(context)


async def test_send_whatsapp_message_missing_connector_instance_is_a_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    executor = send_whatsapp_node.SendWhatsAppMessageExecutor()

    async def fake_get_instance(session: Any, *, tenant_id: uuid.UUID, instance_id: uuid.UUID) -> None:
        return None

    monkeypatch.setattr(send_whatsapp_node.connector_service, "get_instance", fake_get_instance)

    context = _context({"connector_instance_id": str(uuid.uuid4()), "to": "123", "body": "hi"}, {})

    result = await executor.execute(context)

    assert isinstance(result, Failure)
    assert "not found" in result.error


# --------------------------------------------------------------------------
# Action: create_ticket
# --------------------------------------------------------------------------


async def test_create_ticket_config_requires_subject() -> None:
    executor = create_ticket_node.CreateTicketExecutor()
    executor.validate_config({"subject": "Refund request"})
    with pytest.raises(ValidationError):
        executor.validate_config({})


async def test_create_ticket_execute_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    executor = create_ticket_node.CreateTicketExecutor()
    tenant_id = uuid.uuid4()
    created_ticket = Ticket(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        subject="WhatsApp: refund please",
        status=TicketStatus.OPEN,
    )

    captured: dict[str, Any] = {}

    async def fake_create_ticket(session: Any, tid: uuid.UUID, payload: Any) -> Ticket:
        captured["tenant_id"] = tid
        captured["payload"] = payload
        return created_ticket

    monkeypatch.setattr(create_ticket_node.tickets_service, "create_ticket", fake_create_ticket)

    context = ExecutionContext(
        session=None,
        tenant_id=tenant_id,
        run_id=uuid.uuid4(),
        node_id="ticket",
        config={"subject": "WhatsApp: {{trigger.text}}"},
        variables={"trigger": {"text": "refund please"}},
    )

    result = await executor.execute(context)

    assert isinstance(result, Success)
    assert result.output == {"ticket_id": str(created_ticket.id)}
    assert captured["tenant_id"] == tenant_id
    assert captured["payload"].subject == "WhatsApp: refund please"
    assert captured["payload"].customer_id is None


async def test_create_ticket_invalid_customer_id_is_a_failure() -> None:
    executor = create_ticket_node.CreateTicketExecutor()
    context = _context({"subject": "hi", "customer_id": "not-a-uuid"}, {})

    result = await executor.execute(context)

    assert isinstance(result, Failure)
    assert "not a valid UUID" in result.error


async def test_create_ticket_propagates_service_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """See test_send_whatsapp_message_propagates_adapter_exception's
    docstring - same reasoning, this node is also `retryable = True`."""
    executor = create_ticket_node.CreateTicketExecutor()
    assert executor.retryable is True
    assert executor.max_retries == 2

    async def fake_create_ticket(session: Any, tid: uuid.UUID, payload: Any) -> Ticket:
        raise RuntimeError("db exploded")

    monkeypatch.setattr(create_ticket_node.tickets_service, "create_ticket", fake_create_ticket)

    context = _context({"subject": "hi"}, {})

    with pytest.raises(RuntimeError, match="db exploded"):
        await executor.execute(context)
