"""Real Postgres regressions for repeated questions and tenant-wide queue stalls.

Only the disposable TEST_DATABASE_URL is used. Every provider call is mocked.
"""
import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from fusionflow.db.session import set_tenant_context
from fusionflow.modules.workflows.engine import outbox_poller
from fusionflow.modules.workflows.models import RunStatus, WorkflowRun, WorkflowRunStep, WorkflowTrigger, WorkflowTriggerInbox, WorkflowVersion
from fusionflow.modules.workflows.nodes import instagram_collect_text as collect
from tests.conftest import requires_postgres
from tests.test_instagram_reset_postgres import data, queue, dispatch, waiting, reset_graph, original_graph  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.needs_postgres, requires_postgres]


async def configure_form(data, monkeypatch):
    ig = str(data.connectors[0][0])
    graph = {"nodes": [
        {"id": "trigger", "data": {"nodeType": "instagram.postback_received", "config": {}}},
        {"id": "collect-name", "data": {"nodeType": "instagram.collect_text", "config": {
            "connector_instance_id": ig, "recipient_id": "{{trigger.from}}", "question": "What is your name?"}}},
        {"id": "done", "data": {"nodeType": "log.noop", "config": {"message": "Name received"}}},
    ], "edges": [{"id": "a", "source": "trigger", "target": "collect-name"},
                  {"id": "b", "source": "collect-name", "target": "done"}]}
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        version = await s.get(WorkflowVersion, data.versions[0])
        version.graph = version.compiled_graph = graph
        s.add(WorkflowTrigger(tenant_id=data.tenants[0], workflow_id=data.workflows[0],
                             trigger_type="instagram.postback_received", connector_instance_id=data.connectors[0][0], config={}))
        await s.commit()
    send = AsyncMock()
    monkeypatch.setattr(collect.instagram_adapter, "send_direct_message", send)
    return send


async def test_new_button_form_replaces_wait_before_sending_and_next_text_resumes_it(data, monkeypatch):
    send = await configure_form(data, monkeypatch)
    old = await waiting(data)
    other = await waiting(data, sender="other-sender")
    other_connector = await waiting(data, connector=1)
    other_tenant = await waiting(data, tenant=1)
    async def verify_released(**kwargs):
        s = kwargs["session"]
        old_row = await s.get(WorkflowRun, old, populate_existing=True)
        assert old_row.status == RunStatus.CANCELLED and old_row.waiting_correlation_key is None
    send.side_effect = verify_released
    event = await queue(data, "treatment", 1, event_type="instagram.postback_received", dedupe_key="tap-mid")
    assert await dispatch(data) == 1
    send.assert_awaited_once()
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        new = (await s.execute(select(WorkflowRun).where(WorkflowRun.trigger_event_ref == str(event)))).scalar_one()
        new_id = new.id
        assert new.status == RunStatus.WAITING and new.id != old
        assert (await s.get(WorkflowRun, other)).status == RunStatus.WAITING
        assert (await s.get(WorkflowRun, other_connector)).status == RunStatus.WAITING
        assert (await s.get(WorkflowTriggerInbox, event)).processing_error is None
        await set_tenant_context(s, data.tenants[1])
        assert (await s.get(WorkflowRun, other_tenant)).status == RunStatus.WAITING
    # Redelivery of the same button never re-asks or creates another run.
    assert await queue(data, "treatment", 1, event_type="instagram.postback_received", dedupe_key="tap-mid") == event
    assert await dispatch(data) == 0
    await queue(data, "Test name", 2)
    assert await dispatch(data) == 1
    assert send.await_count == 1
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        assert (await s.get(WorkflowRun, new_id)).status == RunStatus.COMPLETED
        step = (await s.execute(select(WorkflowRunStep).where(WorkflowRunStep.workflow_run_id == new_id,
                                                            WorkflowRunStep.node_id == "done"))).scalar_one()
        assert step.input["variables"]["collect-name"]["reply"] == "Test name"


async def test_constraint_error_after_send_is_quarantined_and_later_users_continue(data, monkeypatch):
    send = await configure_form(data, monkeypatch)
    old = await waiting(data)
    # Reproduce the old collect_text behavior by hiding the existing wait.
    monkeypatch.setattr(collect, "find_pending_wait", AsyncMock(return_value=None))
    before = await queue(data, "button", 1, sender="earlier-user", event_type="instagram.postback_received")
    poison = await queue(data, "button", 2, event_type="instagram.postback_received", dedupe_key="poison-mid")
    after = await queue(data, "button", 3, sender="later-user", event_type="instagram.postback_received")
    assert await dispatch(data) == 3
    assert [c.kwargs["recipient_id"] for c in send.call_args_list] == ["earlier-user", "test-sender", "later-user"]
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        failed = await s.get(WorkflowTriggerInbox, poison)
        assert failed.processed_at is not None and "IntegrityError" in failed.processing_error
        assert "23505" in failed.processing_error and "automatic replay disabled" in failed.processing_error
        assert (await s.get(WorkflowRun, old)).status == RunStatus.WAITING
        for row_id in (before, after):
            row = await s.get(WorkflowTriggerInbox, row_id)
            assert row.processed_at and row.processing_error is None
            run = (await s.execute(select(WorkflowRun).where(WorkflowRun.trigger_event_ref == str(row_id)))).scalar_one()
            assert run.status == RunStatus.WAITING
    assert await dispatch(data) == 0
    assert await queue(data, "button", 2, event_type="instagram.postback_received", dedupe_key="poison-mid") == poison
    assert await dispatch(data) == 0 and send.await_count == 3


async def test_worker_interruption_does_not_replay_previous_committed_messages(data, monkeypatch):
    send = await configure_form(data, monkeypatch)
    first = await queue(data, "button", 1, sender="first", event_type="instagram.postback_received")
    second = await queue(data, "button", 2, sender="second", event_type="instagram.postback_received")
    original = outbox_poller._dispatch_inbox_row
    async def interrupted(s, tenant, row):
        if row.id == second: raise asyncio.CancelledError()
        await original(s, tenant, row)
    with monkeypatch.context() as patch:
        patch.setattr(outbox_poller, "_dispatch_inbox_row", interrupted)
        with pytest.raises(asyncio.CancelledError): await dispatch(data)
    send.assert_awaited_once()
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        assert (await s.get(WorkflowTriggerInbox, first)).processed_at is not None
        assert (await s.get(WorkflowTriggerInbox, second)).processed_at is None
    assert await dispatch(data) == 1
    assert [c.kwargs["recipient_id"] for c in send.call_args_list] == ["first", "second"]


async def test_concurrent_workers_do_not_duplicate_queued_button(data, monkeypatch):
    send = await configure_form(data, monkeypatch)
    await waiting(data)
    await queue(data, "button", 1, event_type="instagram.postback_received")
    entered, release = asyncio.Event(), asyncio.Event()
    async def slow_send(**kwargs):
        entered.set()
        await asyncio.wait_for(release.wait(), 5)
    send.side_effect = slow_send
    first = asyncio.create_task(dispatch(data))
    second = None
    try:
        await asyncio.wait_for(entered.wait(), 5)
        second = asyncio.create_task(dispatch(data))
        await asyncio.sleep(0.05)
        assert not second.done()
        release.set()
        results = await asyncio.wait_for(asyncio.gather(first, second), 5)
        assert sum(results) == 1
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
    send.assert_awaited_once()
