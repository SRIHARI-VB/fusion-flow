"""Phone-card regression: actual webhook shape, with synthetic sender/number."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest

from fusionflow.modules.connectors.instagram.adapter import InstagramAdapter
from fusionflow.modules.inbox import service as inbox_service
from fusionflow.modules.workflows.engine import event_bus
from tests.test_clinic_instagram_repair import MemorySession


PHONE_CARD = {"mid": "phone-card-mid", "attachments": [
    {"type": "template", "payload": {"generic": {"elements": []}}},
]}
PHONE_TEXT = {"mid": "phone-text-mid", "text": "+919876543210"}


def webhook(*messages):
    return {"object": "instagram", "entry": [{"id": "clinic", "messaging": [
        {"sender": {"id": "patient"}, "recipient": {"id": "clinic"},
         "timestamp": 1791317152730 + index, "message": message}
        for index, message in enumerate(messages)
    ]}]}


@pytest.mark.parametrize("message", [PHONE_CARD, {"mid": "m"}, {"mid": "m", "text": None},
    {"mid": "m", "text": ""}, {"mid": "m", "text": " \n\t"}, {"mid": "m", "text": 123},
    {"mid": "m", "is_unsupported": True}, {"mid": "m", "is_deleted": True},
    {"mid": "m", "attachments": [{"type": "image", "payload": {"url": "https://example.com/photo.jpg"}}]},
])
def test_textless_events_do_not_become_text_triggers(message):
    assert InstagramAdapter._extract_inbound_message(webhook(message)) is None


@pytest.mark.parametrize("messages", [(PHONE_TEXT, PHONE_CARD), (PHONE_CARD, PHONE_TEXT)])
def test_card_in_same_delivery_does_not_hide_real_phone_text(messages):
    result = InstagramAdapter._extract_inbound_message(webhook(*messages))
    assert result["text"] == PHONE_TEXT["text"] and result["message_id"] == "phone-text-mid"


async def test_phone_and_card_deliveries_queue_only_number_but_keep_both_audit_events(monkeypatch):
    publish, record = AsyncMock(), AsyncMock()
    monkeypatch.setattr(event_bus, "publish_trigger_event", publish)
    monkeypatch.setattr(inbox_service, "upsert_inbound_message", record)
    instance = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4())
    adapter, session = InstagramAdapter(), MemorySession()
    for message in (PHONE_TEXT, PHONE_CARD):
        await adapter.handle_webhook(instance=instance, session=session, headers={},
                                     raw_payload=json.dumps(webhook(message)).encode())
    publish.assert_awaited_once()
    assert publish.call_args.kwargs["payload"]["text"] == PHONE_TEXT["text"]
    assert publish.call_args.kwargs["dedupe_key"] == "phone-text-mid"
    record.assert_awaited_once()
    assert len(session.added) == 2


@pytest.mark.parametrize("quick_reply", [False, True])
def test_real_button_replies_still_route_as_postbacks(quick_reply):
    body = webhook({"mid": "button-mid", "text": "Book a Consultation",
                    "quick_reply": {"payload": "CONCERN_OTHER"}}) if quick_reply else {
        "entry": [{"messaging": [{"sender": {"id": "patient"}, "timestamp": 1,
            "postback": {"mid": "button-mid", "payload": "CONCERN_OTHER", "title": "Book a Consultation"}}]}],
    }
    assert InstagramAdapter._extract_inbound_message(body) is None
    assert InstagramAdapter._extract_postback(body)["payload"] == "CONCERN_OTHER"
