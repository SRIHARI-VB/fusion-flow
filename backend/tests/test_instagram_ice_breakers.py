"""Account-level suggestions can be removed without touching other profile fields."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import httpx
import pytest

from fusionflow.modules.connectors.instagram import adapter as instagram
from tests.test_google_calendar_reconnect import mock_http


QUESTION = {"question": "Welcome to our clinic. How can I help you today?", "payload": "ICE_BREAKER_0"}
LOCALE = {"locale": "default", "call_to_actions": [QUESTION]}


@pytest.fixture
def instance(monkeypatch):
    monkeypatch.setattr(instagram.connector_service, "get_credential_secret",
                        AsyncMock(return_value={"access_token": "test-token"}))
    return SimpleNamespace(id=uuid.uuid4(), provider_ref_ids={"instagram_account_id": "test-clinic"})


@pytest.mark.parametrize("body", [
    {"data": [{"ice_breakers": [LOCALE]}]},  # Observed live profile response.
    {"data": [LOCALE]}, {"ice_breakers": [LOCALE]},
    {"data": [{"ice_breakers": [QUESTION]}]},
    {"data": [{"locale": "fr_FR", "call_to_actions": []}, LOCALE]},
])
async def test_reads_saved_default_questions_from_profile(monkeypatch, instance, body):
    mock_http(monkeypatch, lambda _: httpx.Response(200, json=body))
    assert await instagram.InstagramAdapter().get_ice_breakers(instance=instance, session=None) == [QUESTION]


async def test_removing_all_questions_deletes_only_ice_breakers_and_reads_empty(monkeypatch, instance):
    requests = []
    def respond(request):
        requests.append(request)
        if request.method == "DELETE":
            return httpx.Response(200, json={"result": "success"})
        return httpx.Response(200, json={"data": []})
    mock_http(monkeypatch, respond)
    adapter = instagram.InstagramAdapter()
    await adapter.set_ice_breakers(instance=instance, session=None, questions=[])
    assert await adapter.get_ice_breakers(instance=instance, session=None) == []
    assert [r.method for r in requests] == ["DELETE", "GET"]
    assert requests[0].url.path.endswith("/test-clinic/messenger_profile")
    assert json.loads(requests[0].url.params["fields"]) == ["ice_breakers"]
    assert not requests[0].content


async def test_saving_questions_preserves_post_and_default_locale(monkeypatch, instance):
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"result": "success"})
    mock_http(monkeypatch, respond)
    await instagram.InstagramAdapter().set_ice_breakers(instance=instance, session=None, questions=[QUESTION])
    assert requests[0].method == "POST"
    assert json.loads(requests[0].content) == {"platform": "instagram", "ice_breakers": [LOCALE]}


@pytest.mark.parametrize("operation", ["read", "save", "remove"])
@pytest.mark.parametrize("failure", ["offline", "rejected"])
async def test_failures_never_look_like_saved_or_removed_questions(monkeypatch, instance, operation, failure):
    def respond(request):
        if failure == "offline":
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(400, json={"error": {"message": "Permission denied"}})
    mock_http(monkeypatch, respond)
    adapter = instagram.InstagramAdapter()
    with pytest.raises(ValueError):
        if operation == "read":
            await adapter.get_ice_breakers(instance=instance, session=None)
        else:
            await adapter.set_ice_breakers(instance=instance, session=None,
                                           questions=[QUESTION] if operation == "save" else [])
