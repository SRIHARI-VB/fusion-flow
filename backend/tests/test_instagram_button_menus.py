"""Menu transport, live-list rendering and guarded clinic migration coverage."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import httpx
import pytest

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import ConnectorActionNotRetryable
from fusionflow.modules.connectors.instagram.adapter import InstagramAdapter
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Success
from fusionflow.modules.workflows.nodes import instagram_ask_choice as choice
from scripts.upgrade_clinic_button_menus import button_menus_graph, WELCOME_IDS, TEXT_HINT, RepairError


@pytest.fixture
def transport(monkeypatch):
    requests = []
    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"message_id": f"m-{len(requests)}"})
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(**kw, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(connector_service, "get_credential_secret", AsyncMock(return_value={"access_token": "test-token"}))
    return requests


def instance():
    return SimpleNamespace(id=uuid.uuid4(), provider_ref_ids={"instagram_account_id": "test-account"},
                           connector_type=SimpleNamespace(key="instagram"))


@pytest.mark.parametrize("count", [1, 3, 4, 7, 13, 14])
async def test_sends_every_button_in_order_without_quick_replies(transport, count):
    buttons = [{"title": "Long treatment label number " + str(i), "payload": f"SERVICE:{i}"} for i in range(count)]
    snapshot = deepcopy(buttons)
    await InstagramAdapter().perform_action(action="send_button_template", instance=instance(), session=None,
        params={"recipient_id": "patient", "text": "Pick one", "buttons": buttons})
    assert len(transport) == (count + 2) // 3
    payloads = [r["message"]["attachment"]["payload"] for r in transport]
    assert payloads[0]["text"] == "Pick one"
    assert all(p["text"] == "More options:" for p in payloads[1:])
    assert [b["payload"] for p in payloads for b in p["buttons"]] == [b["payload"] for b in buttons]
    assert all(1 <= len(p["buttons"]) <= 3 and p["template_type"] == "button" for p in payloads)
    assert all(len(b["title"]) <= 20 and b["type"] == "postback" for p in payloads for b in p["buttons"])
    assert all(r["recipient"] == {"id": "patient"} and "quick_replies" not in r["message"] for r in transport)
    assert buttons == snapshot


@pytest.mark.parametrize("bad", [[], [{"title": "Missing payload"}], [None], [{"title": "", "payload": "x"}]])
async def test_invalid_options_send_nothing(transport, bad):
    with pytest.raises(ValueError):
        await InstagramAdapter().send_button_template(instance=instance(), session=None,
            recipient_id="patient", text="Pick", buttons=bad)
    assert transport == []


async def test_late_invalid_option_is_validated_before_first_message(transport):
    with pytest.raises(ValueError):
        await InstagramAdapter().send_button_template(instance=instance(), session=None, recipient_id="patient",
            text="Pick", buttons=[{"title": "OK", "payload": "x"}] * 3 + [{"title": "bad"}])
    assert transport == []


@pytest.mark.parametrize("network", [False, True])
async def test_partial_delivery_cannot_retry_the_entire_menu(monkeypatch, network):
    seen = []
    def handle(request):
        seen.append(request)
        if len(seen) == 2:
            if network:
                raise httpx.ConnectError("offline", request=request)
            return httpx.Response(400, json={"error": {"message": "rejected"}})
        return httpx.Response(200, json={})
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(**kw, transport=httpx.MockTransport(handle)))
    monkeypatch.setattr(connector_service, "get_credential_secret", AsyncMock(return_value={"access_token": "test"}))
    with pytest.raises(ConnectorActionNotRetryable, match="partially delivered"):
        await InstagramAdapter().send_button_template(instance=instance(), session=None, recipient_id="patient",
            text="Pick", buttons=[{"title": "Choice", "payload": str(i)} for i in range(7)])
    assert len(seen) == 2


@pytest.mark.parametrize("count", [0, 1, 3, 4, 7, 14])
async def test_dynamic_services_grow_past_the_old_six_option_limit(monkeypatch, transport, count):
    ig = instance()
    monkeypatch.setattr(connector_service, "get_instance", AsyncMock(return_value=ig))
    monkeypatch.setattr(choice.connector_registry, "get_or_none", lambda _: InstagramAdapter())
    rows = [{"id": str(uuid.uuid4()), "name": f"Service {i}"} for i in range(count)]
    query = AsyncMock(return_value=rows)
    monkeypatch.setattr(choice, "resolve_adapter", AsyncMock(return_value=SimpleNamespace(list=query)))
    monkeypatch.setattr(choice, "_discount_suffix_for", AsyncMock(return_value=" 🎁"))
    context = ExecutionContext(session=None, tenant_id=uuid.uuid4(), run_id=uuid.uuid4(), node_id="services",
        variables={"trigger": {"from": "patient"}}, config={"connector_instance_id": str(ig.id),
        "recipient_id": "{{trigger.from}}", "text": "Services", "source": {"module": "services", "limit": 100}})
    result = await choice.AskChoiceExecutor().execute(context)
    assert isinstance(result, Success) and result.output == {"sent_count": count, "has_more": False}
    sent = [b for r in transport for b in r["message"]["attachment"]["payload"]["buttons"]]
    assert [b["payload"] for b in sent] == [f"services:{r['id']}" for r in rows]
    assert all(b["title"].endswith(" 🎁") for b in sent)
    assert query.call_args.kwargs["tenant_id"] == context.tenant_id


@pytest.fixture
def clinic_graph():
    def node(id, kind, config):
        return {"id": id, "data": {"nodeType": kind, "config": config}}
    options = [{"title": p, "payload": p} for p in ["MENU_CONSULT", "MENU_TREATMENTS", "MENU_INFO", "MENU_SUPPORT"]]
    nodes = [node(i, "connector.action", {"action": "send_quick_replies", "params": {
        "text": "Welcome\n\n" + TEXT_HINT, "replies": deepcopy(options)}}) for i in WELCOME_IDS]
    nodes += [node("dyn-send-services-page" + str(i+1), "instagram.ask_choice", {"source": {
        "module": "services", "offset": 3*i, "limit": 3}, "text": "Services"}) for i in range(2)]
    nodes += [node(f"slot-{i}", "instagram.ask_calendar_slot", {"limit": 13, "offset": 0}) for i in range(12)]
    nodes += [node("intent-router", "condition.multi_branch", {"cases": [{"label": "conversation-reset",
        "field_path": "trigger.conversation_reset", "operator": "eq", "value": True}]})]
    edges = [{"id": "pages", "source": "dyn-send-services-page1", "target": "dyn-send-services-page2"},
             {"id": "reset", "source": "intent-router", "target": "send-main-menu-firsttime", "sourceHandle": "conversation-reset"}]
    return {"nodes": nodes, "edges": edges}


def test_graph_migration_preserves_routing_and_reset(clinic_graph):
    original = deepcopy(clinic_graph)
    fixed = button_menus_graph(clinic_graph)
    assert clinic_graph == original and button_menus_graph(fixed) == fixed
    assert len(fixed["nodes"]) == len(original["nodes"]) - 1
    assert fixed["edges"] == [original["edges"][1]]
    for node in fixed["nodes"]:
        c = node["data"]["config"]
        if node["id"] in WELCOME_IDS:
            assert c["action"] == "send_button_template" and c["params"]["text"] == "Welcome"
            assert "replies" not in c["params"] and len(c["params"]["buttons"]) == 4
        if node["data"]["nodeType"] == "instagram.ask_calendar_slot":
            assert c["limit"] == 288
    assert fixed["nodes"][-1] == original["nodes"][-1]


@pytest.mark.parametrize("drift", ["payload", "page_edge", "page_reference", "slot_limit", "slot_missing"])
def test_graph_migration_rejects_unreviewed_changes(clinic_graph, drift):
    if drift == "payload": clinic_graph["nodes"][0]["data"]["config"]["params"]["replies"][0]["payload"] = "different"
    if drift == "page_edge": clinic_graph["edges"].append({"source": "dyn-send-services-page2", "target": "other"})
    if drift == "page_reference": clinic_graph["nodes"][0]["data"]["config"]["params"]["text"] = "{{dyn-send-services-page2.sent_count}}"
    if drift == "slot_limit": clinic_graph["nodes"][5]["data"]["config"]["limit"] = 7
    if drift == "slot_missing": clinic_graph["nodes"].pop(5)
    with pytest.raises(RepairError): button_menus_graph(clinic_graph)
