"""Real transactional /clear coverage against a disposable TEST_DATABASE_URL.

No provider calls: only the outbound adapter and entitlement checks are mocked.
Run migrations through 0039 first and use a non-BYPASSRLS test role.
"""

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from sqlalchemy import delete, select, text

from fusionflow.db.session import set_tenant_context
from fusionflow.modules.business_objects.models import ObjectRecord, ObjectTypeDefinition
from fusionflow.modules.connectors.base import registry
from fusionflow.modules.connectors.models import ConnectorCategory, ConnectorInstance, ConnectorType
from fusionflow.modules.customers.models import Customer
from fusionflow.modules.inbox.models import Conversation
from fusionflow.modules.tenancy.models import Business
from fusionflow.modules.tickets.models import Ticket
from fusionflow.modules.workflows.engine import entitlement, event_bus, outbox_poller
from fusionflow.modules.workflows.engine.conversation_reset import RESET_ACK
from fusionflow.modules.workflows.engine.run_loop import DELAY_CORRELATION_KEY
from fusionflow.modules.workflows.models import (
    RunStatus, Workflow, WorkflowRun, WorkflowTrigger, WorkflowTriggerInbox, WorkflowVersion,
)
from tests.conftest import requires_postgres
from tests.test_instagram_conversation_reset import reset_graph
from tests.test_clinic_instagram_repair import original_graph

pytestmark = [pytest.mark.asyncio, pytest.mark.needs_postgres, requires_postgres]
BASE = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture
async def data(pg_session_factory, reset_graph, monkeypatch):
    send = AsyncMock(return_value={"ok": True})
    adapter = SimpleNamespace(perform_action=send)
    monkeypatch.setattr(registry, "get", lambda _: adapter)
    monkeypatch.setattr(registry, "get_or_none", lambda _: adapter)
    monkeypatch.setattr(entitlement, "first_block_message", AsyncMock(return_value=None))
    tenants, connectors, workflows, versions, customers = [], [], [], [], []
    catalog_id = uuid.uuid4()
    async with pg_session_factory() as s:
        role = (await s.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"))).one()
        assert not role.rolsuper and not role.rolbypassrls
        s.add(ConnectorType(id=catalog_id, key=f"reset-test-{catalog_id.hex}", category=ConnectorCategory.SOCIAL,
                            display_name="Reset test"))
        await s.flush()
        for _ in range(2):
            tenant = uuid.uuid4()
            tenants.append(tenant)
            s.add(Business(id=tenant, name="Reset test tenant", slug=f"reset-{tenant.hex}"))
            await s.flush()
            await set_tenant_context(s, tenant)
            instances = [uuid.uuid4(), uuid.uuid4()]
            connectors.append(instances)
            for instance in instances:
                s.add(ConnectorInstance(id=instance, tenant_id=tenant, connector_type_id=catalog_id, display_name="Test IG"))
                for sender in ("test-sender", "other-sender"):
                    s.add(Conversation(tenant_id=tenant, connector_instance_id=instance, external_contact_id=sender))
            customer = Customer(id=uuid.uuid4(), tenant_id=tenant, external_ref="test-sender", name="Existing patient", custom_fields={"retained": "yes"})
            s.add(customer)
            customers.append(customer.id)
            workflow = Workflow(id=uuid.uuid4(), tenant_id=tenant, name="Reset test", status="published")
            s.add(workflow)
            await s.flush()
            graph = deepcopy(reset_graph)
            for node in graph["nodes"]:
                if "connector_instance_id" in node["data"]["config"]:
                    node["data"]["config"]["connector_instance_id"] = str(instances[0])
            version = WorkflowVersion(id=uuid.uuid4(), tenant_id=tenant, workflow_id=workflow.id, version_number=1,
                                      graph=graph, compiled_graph=graph, published_at=BASE)
            s.add(version)
            await s.flush()
            workflow.current_published_version_id = version.id
            s.add(WorkflowTrigger(tenant_id=tenant, workflow_id=workflow.id,
                                  trigger_type="instagram.message_received", connector_instance_id=instances[0], config={}))
            workflows.append(workflow.id)
            versions.append(version.id)
            await s.flush()
        await s.commit()
    result = SimpleNamespace(factory=pg_session_factory, tenants=tenants, connectors=connectors,
                             workflows=workflows, versions=versions, customers=customers, send=send)
    try:
        yield result
    finally:
        async with pg_session_factory() as s:
            await s.execute(delete(Business).where(Business.id.in_(tenants)))
            await s.execute(delete(ConnectorType).where(ConnectorType.id == catalog_id))
            await s.commit()


async def queue(data, text_value, seconds, *, sender="test-sender", tenant=0, connector=0,
                event_type="instagram.message_received", dedupe_key=None):
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[tenant])
        row = await event_bus.publish_trigger_event(
            s, tenant_id=data.tenants[tenant], connector_instance_id=data.connectors[tenant][connector],
            event_type=event_type, payload={"from": sender, "text": text_value,
                "timestamp": int((BASE + timedelta(seconds=seconds)).timestamp() * 1000)},
            dedupe_key=dedupe_key or f"test-{uuid.uuid4()}",
        )
        # Separate receipt times also make ordering deterministic for a batch
        # constructed inside a single DB transaction by a test.
        await s.commit()
        return row.id


async def dispatch(data, tenant=0):
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[tenant])
        return await outbox_poller.process_pending_now(s, data.tenants[tenant])


async def waiting(data, *, tenant=0, connector=0, sender="test-sender", delay=False, status=RunStatus.WAITING):
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[tenant])
        source = WorkflowTriggerInbox(id=uuid.uuid4(), tenant_id=data.tenants[tenant], event_type="instagram.message_received",
            connector_instance_id=data.connectors[tenant][connector], payload={"from": sender}, processed_at=BASE)
        s.add(source)
        run = WorkflowRun(id=uuid.uuid4(), tenant_id=data.tenants[tenant], workflow_id=data.workflows[tenant],
            workflow_version_id=data.versions[tenant], trigger_event_ref=str(source.id), status=status,
            waiting_connector_instance_id=None if delay else data.connectors[tenant][connector],
            waiting_correlation_key=DELAY_CORRELATION_KEY if delay else sender,
            waiting_node_id="collect-name", waiting_frontier=["next"],
            waiting_variables={"trigger": {"from": sender}, "temporary-answer": "draft answer"},
            waiting_expires_at=BASE + timedelta(days=365))
        s.add(run)
        await s.commit()
        return run.id


async def test_clear_then_immediate_hi_starts_initial_flow_and_consumes_flag_once(data):
    old_run = await waiting(data)
    clear = await queue(data, "/clear", 1, dedupe_key="clear-mid")
    await queue(data, "Hi", 2)
    assert await dispatch(data) == 2
    assert [c.kwargs["params"]["text"] for c in data.send.call_args_list] == [RESET_ACK, "Welcome to our clinic!"]
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        old = await s.get(WorkflowRun, old_run)
        assert old.status == RunStatus.CANCELLED and old.waiting_variables is None and old.waiting_frontier is None
        customer = await s.get(Customer, data.customers[0])
        assert customer.name == "Existing patient" and customer.custom_fields == {"retained": "yes"}
        assert len((await s.execute(select(Customer))).scalars().all()) == 1
    # The provider retry must neither acknowledge nor reset a second time.
    assert await queue(data, "/clear", 1, dedupe_key="clear-mid") == clear
    assert await dispatch(data) == 0
    await queue(data, "Hi", 3)
    await dispatch(data)
    assert data.send.call_args.kwargs["params"]["text"].startswith("Welcome back!")


async def test_reset_is_scoped_and_preserves_submitted_records(data):
    target = await waiting(data)
    delayed = await waiting(data, delay=True)
    other_sender = await waiting(data, sender="other-sender")
    other_connection = await waiting(data, connector=1)
    other_tenant = await waiting(data, tenant=1)
    completed = await waiting(data, status=RunStatus.COMPLETED)
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        kind = ObjectTypeDefinition(id=uuid.uuid4(), tenant_id=data.tenants[0], key="appointment", name="Appointment")
        s.add(kind)
        await s.flush()
        for status, run_id in [("draft", target), ("requested", target), ("confirmed", target), ("draft", completed)]:
            s.add(ObjectRecord(tenant_id=data.tenants[0], object_type_id=kind.id, customer_id=data.customers[0],
                               created_by_run_id=run_id, payload={"status": status}))
        s.add(Ticket(tenant_id=data.tenants[0], customer_id=data.customers[0], subject="Retained history"))
        await s.commit()
    await queue(data, "/clear", 1)
    await dispatch(data)
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        for run_id in (target, delayed):
            assert (await s.get(WorkflowRun, run_id)).status == RunStatus.CANCELLED
        for run_id in (other_sender, other_connection):
            assert (await s.get(WorkflowRun, run_id)).status == RunStatus.WAITING
        assert (await s.get(WorkflowRun, completed)).status == RunStatus.COMPLETED
        records = (await s.execute(select(ObjectRecord))).scalars().all()
        assert sorted(r.payload["status"] for r in records) == ["confirmed", "draft", "requested"]
        assert len((await s.execute(select(Ticket))).scalars().all()) == 1
        assert await s.get(WorkflowRun, other_tenant) is None  # Actual RLS isolation.
        await set_tenant_context(s, data.tenants[1])
        assert (await s.get(WorkflowRun, other_tenant)).status == RunStatus.WAITING


async def test_late_messages_old_resume_and_button_taps_do_not_revive_cancelled_flow(data):
    old = await waiting(data)
    await queue(data, "/clear", 10)
    await dispatch(data)
    await queue(data, "old answer", 9)
    await queue(data, "old button", 9, event_type="instagram.postback_received")
    await queue(data, "new tap on old menu", 11, event_type="instagram.postback_received")
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        await event_bus.publish_trigger_event(s, tenant_id=data.tenants[0], event_type="workflow.resume",
            payload={"run_id": str(old), "reply": {"text": "old queued answer"}})
        await s.commit()
    await dispatch(data)
    assert data.send.await_count == 1
    await queue(data, "Hi", 12)
    await dispatch(data)
    assert data.send.call_args.kwargs["params"]["text"] == "Welcome to our clinic!"


async def test_clear_with_no_wait_releases_handoff_and_ack_failure_keeps_reset(data):
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        conversation = (await s.execute(select(Conversation).where(
            Conversation.connector_instance_id == data.connectors[0][0],
            Conversation.external_contact_id == "test-sender"))).scalar_one()
        conversation.automation_paused = True
        await s.commit()
    data.send.side_effect = RuntimeError("provider unavailable")
    await queue(data, "/clear", 1)
    await dispatch(data)
    data.send.side_effect = None
    await queue(data, "Hi", 2)
    await dispatch(data)
    assert data.send.call_args.kwargs["params"]["text"] == "Welcome to our clinic!"


async def test_normal_message_still_resumes_existing_wait(data, monkeypatch):
    run_id = await waiting(data)
    resume = AsyncMock()
    monkeypatch.setattr(outbox_poller, "resume_run", resume)
    await queue(data, "An ordinary answer", 1)
    await dispatch(data)
    resume.assert_awaited_once()
    assert resume.call_args.args[1].id == run_id
    assert resume.call_args.kwargs["reply_payload"]["text"] == "An ordinary answer"
    data.send.assert_not_awaited()


async def test_concurrent_dispatchers_wait_for_clear_before_processing_hi(data):
    await waiting(data)
    await queue(data, "/clear", 1)
    acknowledging, release = asyncio.Event(), asyncio.Event()
    async def hold_ack(**kwargs):
        if kwargs["params"]["text"] == RESET_ACK:
            acknowledging.set()
            await asyncio.wait_for(release.wait(), 5)
        return {"ok": True}
    data.send.side_effect = hold_ack
    first = asyncio.create_task(dispatch(data))
    second = None
    try:
        await asyncio.wait_for(acknowledging.wait(), 5)
        await queue(data, "Hi", 2)
        second = asyncio.create_task(dispatch(data))
        await asyncio.sleep(0.05)
        assert not second.done()
        release.set()
        assert await asyncio.wait_for(first, 5) == 1
        assert await asyncio.wait_for(second, 5) == 1
    finally:
        release.set()
        await asyncio.gather(first, *([second] if second else []), return_exceptions=True)
    assert [c.kwargs["params"]["text"] for c in data.send.call_args_list] == [RESET_ACK, "Welcome to our clinic!"]


async def test_webhook_session_refreshes_conversation_changed_by_another_worker(data):
    # Serverless dispatch reuses the webhook's session, whose identity map
    # can contain the conversation from before another worker handled /clear.
    async with data.factory() as cached_session:
        await set_tenant_context(cached_session, data.tenants[0])
        cached = (await cached_session.execute(select(Conversation).where(
            Conversation.connector_instance_id == data.connectors[0][0],
            Conversation.external_contact_id == "test-sender"))).scalar_one()
        assert not cached.flow_reset_pending
        await cached_session.commit()
        await queue(data, "/clear", 1)
        await dispatch(data)
        await queue(data, "Hi", 2)
        await set_tenant_context(cached_session, data.tenants[0])
        await outbox_poller.process_pending_now(cached_session, data.tenants[0])
    assert data.send.call_args.kwargs["params"]["text"] == "Welcome to our clinic!"


async def test_two_messages_in_one_batch_consume_reset_only_once(data):
    await queue(data, "/clear", 1)
    await queue(data, "Hi", 2)
    await queue(data, "Hi", 3)
    await dispatch(data)
    texts = [c.kwargs["params"]["text"] for c in data.send.call_args_list]
    assert texts[:2] == [RESET_ACK, "Welcome to our clinic!"]
    assert texts[2].startswith("Welcome back!")
