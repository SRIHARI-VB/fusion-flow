"""Regression for the clinic's extra phone card restarting the welcome flow.

Only disposable Postgres and mocked outbound Instagram messages are used.
"""
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from fusionflow.db.session import set_tenant_context
from fusionflow.modules.customers.models import Customer
from fusionflow.modules.inbox.models import Conversation
from fusionflow.modules.workflows.engine import event_bus
from fusionflow.modules.workflows.models import RunStatus, WorkflowRun, WorkflowRunStep, WorkflowTrigger, WorkflowTriggerInbox, WorkflowVersion
from fusionflow.modules.workflows.nodes import instagram_collect_text as collect
from tests.conftest import requires_postgres
from tests.test_instagram_reset_postgres import data, queue, dispatch, reset_graph, original_graph  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.needs_postgres, requires_postgres]


async def phone_form(data, monkeypatch):
    ig = str(data.connectors[0][0])
    # A genuine phone wait, profile update and the next booking menu.
    graph = {"nodes": [
        {"id": "trigger", "data": {"nodeType": "instagram.postback_received", "config": {}}},
        {"id": "phone", "data": {"nodeType": "instagram.collect_text", "config": {
            "connector_instance_id": ig, "recipient_id": "{{trigger.from}}", "question": "What is the patient's phone number?"}}},
        {"id": "save", "data": {"nodeType": "records.upsert", "config": {
            "module": "customers", "operation": "update", "item_id": str(data.customers[0]), "fields": {"phone": "{{phone.reply}}"}}}},
        {"id": "continue", "data": {"nodeType": "connector.action", "config": {
            "connector_instance_id": ig, "action": "send_button_template", "params": {
                "recipient_id": "{{trigger.from}}", "text": "Ready to book a consultation?",
                "buttons": [{"title": "Book a Consultation", "payload": "CONCERN_OTHER"}],
            }}}},
    ], "edges": [{"id": "a", "source": "trigger", "target": "phone"},
                  {"id": "b", "source": "phone", "target": "save"},
                  {"id": "c", "source": "save", "target": "continue"}]}
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        version = await s.get(WorkflowVersion, data.versions[0])
        version.graph = version.compiled_graph = graph
        s.add(WorkflowTrigger(tenant_id=data.tenants[0], workflow_id=data.workflows[0],
            trigger_type="instagram.postback_received", connector_instance_id=data.connectors[0][0], config={}))
        await s.commit()
    send = AsyncMock()
    monkeypatch.setattr(collect.instagram_adapter, "send_direct_message", send)
    await queue(data, "start-form", 1, event_type="instagram.postback_received")
    await dispatch(data)
    return send


@pytest.mark.parametrize("card_first", [True, False])
async def test_phone_card_never_consumes_number_wait_or_restarts_flow(data, monkeypatch, card_first):
    question = await phone_form(data, monkeypatch)
    if card_first:
        await queue(data, None, 2, dedupe_key="card-mid")
        assert await dispatch(data) == 1
        async with data.factory() as s:
            await set_tenant_context(s, data.tenants[0])
            run = (await s.execute(select(WorkflowRun))).scalar_one()
            assert run.status == RunStatus.WAITING and run.waiting_node_id == "phone"
            assert (await s.get(Customer, data.customers[0])).phone is None
    await queue(data, "+919876543210", 3, dedupe_key="phone-mid")
    if not card_first:
        await queue(data, None, 4, dedupe_key="card-mid")
    await dispatch(data)
    question.assert_awaited_once()
    data.send.assert_awaited_once()
    assert data.send.call_args.kwargs["params"]["text"] == "Ready to book a consultation?"
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        assert (await s.get(Customer, data.customers[0])).phone == "+919876543210"
        runs = (await s.execute(select(WorkflowRun))).scalars().all()
        assert len(runs) == 1 and runs[0].status == RunStatus.COMPLETED
        save = (await s.execute(select(WorkflowRunStep).where(WorkflowRunStep.node_id == "save"))).scalar_one()
        assert save.input["variables"]["phone"]["reply"] == "+919876543210"
    await queue(data, "+919876543210", 3, dedupe_key="phone-mid")
    await queue(data, None, 4, dedupe_key="card-mid")
    assert await dispatch(data) == 0
    assert question.await_count == data.send.await_count == 1


async def test_textless_event_after_clear_keeps_fresh_welcome_for_actual_hi(data):
    await queue(data, "/clear", 1)
    await dispatch(data)
    data.send.reset_mock()
    await queue(data, None, 2)
    await queue(data, " \n", 3)
    await dispatch(data)
    data.send.assert_not_awaited()
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        c = (await s.execute(select(Conversation).where(
            Conversation.connector_instance_id == data.connectors[0][0],
            Conversation.external_contact_id == "test-sender"))).scalar_one()
        assert c.flow_reset_pending
    await queue(data, "Hi", 4)
    await dispatch(data)
    assert data.send.call_args.kwargs["params"]["text"] == "Welcome to our clinic!"


async def test_legacy_empty_resume_row_does_not_erase_phone_wait(data, monkeypatch):
    await phone_form(data, monkeypatch)
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        run = (await s.execute(select(WorkflowRun))).scalar_one()
        run_id = run.id
        row = await event_bus.publish_resume_event(s, run=run, reply_payload={"text": None}, dedupe_key="legacy-card")
        row_id = row.id
        await s.commit()
    await dispatch(data)
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        run = await s.get(WorkflowRun, run_id)
        assert run.status == RunStatus.WAITING and run.waiting_node_id == "phone"
        assert (await s.get(WorkflowTriggerInbox, row_id)).processing_error is None
    await queue(data, "+919876543210", 3)
    await dispatch(data)
    data.send.assert_awaited_once()
