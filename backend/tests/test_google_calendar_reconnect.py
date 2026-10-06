"""OAuth rejection is terminal; availability stays live and patients get a notice."""
from datetime import datetime, timezone
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import httpx
import pytest

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.google import oauth
from fusionflow.modules.connectors.google_calendar.adapter import GoogleCalendarAdapter
from fusionflow.modules.connectors.models import ConnectorState, HealthStatus
from fusionflow.modules.workflows.engine import entitlement, run_loop
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Failure, Success
from fusionflow.modules.workflows.models import RunStatus, WorkflowRun
from fusionflow.modules.workflows.nodes import instagram_ask_calendar_slot as slots


class MemorySession:
    def __init__(self): self.added = []
    def add(self, obj): self.added.append(obj)
    async def flush(self): pass


def instance(key="google_calendar"):
    return SimpleNamespace(id=uuid.uuid4(), connector_type=SimpleNamespace(key=key),
        state=ConnectorState.CONNECTED, health_status=HealthStatus.HEALTHY, last_error_message=None)


@pytest.fixture
def credentials(monkeypatch):
    secret = {"access_token": "old-access", "refresh_token": "old-refresh", "expires_at": 0}
    monkeypatch.setattr(oauth, "settings", SimpleNamespace(google_configured=True, GOOGLE_CLIENT_ID="client",
        GOOGLE_CLIENT_SECRET="secret", GOOGLE_OAUTH_TOKEN_URL="https://oauth.example/token"))
    monkeypatch.setattr(connector_service, "get_credential_secret", AsyncMock(return_value=secret))
    store = AsyncMock()
    monkeypatch.setattr(connector_service, "upsert_credential", store)
    return secret, store


def mock_http(monkeypatch, handler):
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(**kw, transport=httpx.MockTransport(handler)))


async def test_invalid_grant_marks_connector_and_stops_future_refresh_attempts(monkeypatch, credentials):
    calls = []
    def reject(request):
        calls.append(request)
        return httpx.Response(400, json={"error": "invalid_grant", "error_description": "Expired or revoked"})
    mock_http(monkeypatch, reject)
    cal = instance()
    for _ in range(2):
        with pytest.raises(oauth.GoogleReconnectRequired, match="Reconnect"):
            await oauth.get_valid_access_token(MemorySession(), instance=cal)
    assert len(calls) == 1
    assert cal.state == ConnectorState.ACTION_REQUIRED and cal.health_status == HealthStatus.DOWN
    assert "old-refresh" not in cal.last_error_message
    credentials[1].assert_not_awaited()


async def test_client_config_error_does_not_claim_patient_grant_was_revoked(monkeypatch, credentials):
    mock_http(monkeypatch, lambda r: httpx.Response(401, json={"error": "invalid_client"}))
    cal = instance()
    with pytest.raises(ValueError, match="invalid_client") as exc:
        await oauth.get_valid_access_token(MemorySession(), instance=cal)
    assert not isinstance(exc.value, oauth.GoogleReconnectRequired)
    assert cal.state == ConnectorState.CONNECTED


async def test_transient_refresh_failure_never_replaces_credentials_with_stub(monkeypatch, credentials):
    def fail(request): raise httpx.ConnectError("offline", request=request)
    mock_http(monkeypatch, fail)
    cal = instance()
    with pytest.raises(httpx.ConnectError):
        await oauth.get_valid_access_token(MemorySession(), instance=cal)
    credentials[1].assert_not_awaited()
    assert cal.state == ConnectorState.CONNECTED


async def test_successful_refresh_retains_refresh_token(monkeypatch, credentials):
    mock_http(monkeypatch, lambda r: httpx.Response(200, json={"access_token": "new-access", "expires_in": 3600}))
    token = await oauth.get_valid_access_token(MemorySession(), instance=instance())
    assert token == "new-access"
    secret = credentials[1].call_args.kwargs["secret"]
    assert secret["refresh_token"] == "old-refresh" and secret["access_token"] == "new-access"


async def test_fresh_token_after_reconnection_is_usable(monkeypatch, credentials):
    credentials[0].update(access_token="reconnected", expires_at=4102444800)
    refresh = AsyncMock()
    monkeypatch.setattr(oauth, "refresh_access_token", refresh)
    assert await oauth.get_valid_access_token(MemorySession(), instance=instance()) == "reconnected"
    refresh.assert_not_awaited()


async def test_missing_refresh_token_requires_reconnection(credentials):
    credentials[0].pop("refresh_token")
    cal = instance()
    with pytest.raises(oauth.GoogleReconnectRequired):
        await oauth.get_valid_access_token(MemorySession(), instance=cal)
    assert cal.state == ConnectorState.ACTION_REQUIRED


def slot_config(ig, cal, **kw):
    return {"instagram_connector_instance_id": str(ig.id), "calendar_connector_instance_id": str(cal.id),
        "recipient_id": "{{trigger.from}}", "text": "Choose a time", "date": "2099-01-01",
        "period_start": "09:00", "period_end": "17:00", "slot_minutes": "30", "limit": 288,
        "context": "Consultation", **kw}


def node(id, kind, config):
    return {"id": id, "data": {"nodeType": kind, "config": config}}


@pytest.mark.parametrize("kind", ["instagram.ask_calendar_slot", "connector.action"])
async def test_revoked_calendar_fails_once_and_never_reaches_confirmation(monkeypatch, credentials, kind):
    refreshes = []
    def reject(request):
        refreshes.append(request)
        return httpx.Response(400, json={"error": "invalid_grant"})
    mock_http(monkeypatch, reject)
    cal, ig = instance(), instance("instagram")
    send = AsyncMock(return_value={})
    async def lookup(session, *, tenant_id, instance_id): return cal if instance_id == cal.id else ig
    monkeypatch.setattr(connector_service, "get_instance", lookup)
    monkeypatch.setattr(slots.connector_registry, "get_or_none", lambda key: GoogleCalendarAdapter() if key == "google_calendar" else SimpleNamespace(perform_action=send))
    monkeypatch.setattr(entitlement, "first_block_message", AsyncMock(return_value=None))
    sleep = AsyncMock()
    monkeypatch.setattr(run_loop.asyncio, "sleep", sleep)
    config = slot_config(ig, cal) if kind == "instagram.ask_calendar_slot" else {
        "connector_instance_id": str(cal.id), "action": "list_events", "params": {}}
    graph = WorkflowGraph.from_json({"nodes": [node("trigger", "manual.test_trigger", {}), node("pick", kind, config),
        node("confirm", "connector.action", {"connector_instance_id": str(ig.id), "action": "send_direct_message",
                                             "params": {"text": "Booked", "recipient_id": "patient"}})],
        "edges": [{"id": "a", "source": "trigger", "target": "pick"}, {"id": "b", "source": "pick", "target": "confirm"}]})
    record = WorkflowRun(id=uuid.uuid4(), tenant_id=uuid.uuid4(), workflow_id=uuid.uuid4(),
        workflow_version_id=uuid.uuid4(), status=RunStatus.RUNNING, loop_guard_count=0, started_at=datetime.now(timezone.utc))
    session = MemorySession()
    await run_loop.execute_run(session, record, graph, trigger_payload={"from": "patient"})
    assert record.status == RunStatus.FAILED
    assert session.added[-1].node_id == "pick" and session.added[-1].attempt == 1
    assert len(refreshes) == 1 and cal.state == ConnectorState.ACTION_REQUIRED
    sleep.assert_not_awaited()
    if kind == "instagram.ask_calendar_slot":
        send.assert_awaited_once()
        call = send.call_args.kwargs
        assert call["action"] == "send_direct_message" and call["params"]["recipient_id"] == "patient"
        assert "temporarily unavailable" in call["params"]["text"] and "Google" not in call["params"]["text"]
    else:
        send.assert_not_awaited()


async def test_slots_send_all_available_choices_as_buttons(monkeypatch):
    cal, ig = instance(), instance("instagram")
    async def lookup(session, *, tenant_id, instance_id): return cal if instance_id == cal.id else ig
    monkeypatch.setattr(connector_service, "get_instance", lookup)
    busy = AsyncMock(return_value={"items": [{"start": {"dateTime": "2099-01-01T10:00:00+05:30"},
                                             "end": {"dateTime": "2099-01-01T10:30:00+05:30"}}]})
    send = AsyncMock()
    monkeypatch.setattr(slots.connector_registry, "get_or_none", lambda key: SimpleNamespace(perform_action=busy if key == "google_calendar" else send))
    context = ExecutionContext(session=MemorySession(), tenant_id=uuid.uuid4(), run_id=uuid.uuid4(), node_id="slots",
        config=slot_config(ig, cal), variables={"trigger": {"from": "patient"}})
    result = await slots.AskCalendarSlotExecutor().execute(context)
    assert isinstance(result, Success) and result.output == {"sent_count": 15, "has_more": False}
    call = send.call_args.kwargs
    assert call["action"] == "send_button_template" and "replies" not in call["params"]
    buttons = call["params"]["buttons"]
    assert len(buttons) == 15 and buttons[-1]["payload"].endswith("|2099-01-01T17:00:00+05:30")
    assert not any("|2099-01-01T10:00:00+05:30|" in b["payload"] for b in buttons)
    assert busy.call_args.kwargs["params"]["require_live"] is True


async def test_live_availability_outage_does_not_become_empty_calendar(monkeypatch):
    monkeypatch.setattr(oauth, "get_valid_access_token", AsyncMock(return_value="real-access"))
    def fail(request): raise httpx.ConnectError("offline", request=request)
    mock_http(monkeypatch, fail)
    with pytest.raises(httpx.ConnectError):
        await GoogleCalendarAdapter().list_events(instance(), MemorySession(), require_live=True)


async def test_live_availability_rejects_stub_token(monkeypatch):
    monkeypatch.setattr(oauth, "get_valid_access_token", AsyncMock(return_value="stub-access-token-test"))
    with pytest.raises(RuntimeError, match="requires a connected Google account"):
        await GoogleCalendarAdapter().list_events(instance(), MemorySession(), require_live=True)
