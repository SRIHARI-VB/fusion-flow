"""Patient booking/check-in and /clear integration using disposable, RLS-enforced PostgreSQL."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from fusionflow.db.session import set_tenant_context
from fusionflow.modules.business_objects.models import ObjectRecord, ObjectTypeDefinition
from fusionflow.modules.clinic_queue import service as clinic
from fusionflow.modules.clinic_queue.models import PatientVisit, PatientVisitStage
from fusionflow.modules.clinic_queue.schemas import PatientCreate
from fusionflow.modules.customers.models import Customer
from fusionflow.modules.workflows.engine.appointment_reset import CALENDAR_CANCEL_EVENT
from fusionflow.modules.workflows.models import RunStatus, StepStatus, WorkflowRunStep, WorkflowTriggerInbox, WorkflowVersion
from fusionflow.modules.workflows.engine.registry import ExecutionContext, Success
from fusionflow.modules.workflows.nodes.record_upsert import RecordUpsertExecutor
from fusionflow.modules.workflows.nodes.module_create import ModuleCreateExecutor
from tests.conftest import requires_postgres
from tests.test_instagram_reset_postgres import data, queue, dispatch, waiting, reset_graph, original_graph  # noqa: F401

pytestmark = [pytest.mark.asyncio, pytest.mark.needs_postgres, requires_postgres]


async def booking(data, *, run_id=None, tenant=0, status="confirmed", payload=None):
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[tenant])
        kind = (await s.execute(select(ObjectTypeDefinition).where(ObjectTypeDefinition.key == "appointment"))).scalar_one_or_none()
        if kind is None:
            kind = ObjectTypeDefinition(tenant_id=data.tenants[tenant], key="appointment", name="Appointment")
            s.add(kind)
            await s.flush()
        record = ObjectRecord(tenant_id=data.tenants[tenant], object_type_id=kind.id, customer_id=data.customers[tenant],
            created_by_run_id=run_id, payload={"status": status, "customer_name": "Booking Patient",
                "customer_phone": "+919876543210", **(payload or {})})
        s.add(record)
        await s.commit()
        return record.id


async def test_clear_removes_bookings_but_preserves_clinical_visits_and_other_scopes(data):
    run = await waiting(data, status=RunStatus.COMPLETED)
    removable = await booking(data, run_id=run)
    protected = await booking(data, run_id=run)
    manual = await booking(data)
    other_tenant = await booking(data, tenant=1)
    other_run = await waiting(data, connector=1, status=RunStatus.COMPLETED)
    other_connection = await booking(data, run_id=other_run)
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        visits = []
        for ref, stage in [(removable, PatientVisitStage.RECEPTION), (protected, PatientVisitStage.COMPLETED)]:
            v = PatientVisit(tenant_id=data.tenants[0], customer_id=data.customers[0], appointment_ref_id=ref,
                patient_name="Snapshot Patient", patient_phone="1234567890", stage=stage,
                checked_in_at=datetime.now(timezone.utc), consultation_notes="Preserved care")
            s.add(v); visits.append(v)
        await s.commit()
        visit_ids = [v.id for v in visits]
    await queue(data, "/clear", 1)
    await dispatch(data)
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        assert await s.get(ObjectRecord, removable) is None
        for ref in (protected, manual, other_connection):
            assert await s.get(ObjectRecord, ref) is not None
        active_visit = await s.get(PatientVisit, visit_ids[0])
        assert active_visit.appointment_ref_id is None and active_visit.consultation_notes == "Preserved care"
        completed_visit = await s.get(PatientVisit, visit_ids[1])
        assert completed_visit.appointment_ref_id == protected
        assert await s.get(ObjectRecord, other_tenant) is None
        await set_tenant_context(s, data.tenants[1])
        assert await s.get(ObjectRecord, other_tenant) is not None


async def test_calendar_failure_is_durable_and_does_not_replay_clear_or_block_hi(data, monkeypatch):
    from fusionflow.modules.connectors import service as connectors
    from fusionflow.modules.connectors.google_calendar.adapter import adapter
    run = await waiting(data, status=RunStatus.COMPLETED)
    calendar = uuid.uuid4()
    record_id = await booking(data, run_id=run, payload={"calendar_event_id": "event-1", "calendar_connector_instance_id": str(calendar)})
    original_get = connectors.get_instance
    async def get_instance(s, *, tenant_id, instance_id):
        if instance_id == calendar:
            return SimpleNamespace(id=calendar, connector_type=SimpleNamespace(key="google_calendar"))
        return await original_get(s, tenant_id=tenant_id, instance_id=instance_id)
    monkeypatch.setattr(connectors, "get_instance", get_instance)
    cancel = AsyncMock(side_effect=RuntimeError("Google reconnect required"))
    monkeypatch.setattr(adapter, "delete_event", cancel)
    await queue(data, "/clear", 1)
    await queue(data, "Hi", 2)
    assert await dispatch(data) == 3  # clear, Hi, first cancellation attempt
    assert data.send.await_count == 2
    assert data.send.call_args.kwargs["params"]["text"] == "Welcome to our clinic!"
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        assert await s.get(ObjectRecord, record_id) is None
        row = (await s.execute(select(WorkflowTriggerInbox).where(WorkflowTriggerInbox.event_type == CALENDAR_CANCEL_EVENT))).scalar_one()
        assert row.processed_at is None and row.available_at and "pending" in row.processing_error
        retry_id = row.id
    assert await dispatch(data) == 0  # Backoff doesn't monopolize the tenant lock.
    cancel.side_effect = None
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        row = await s.get(WorkflowTriggerInbox, retry_id)
        row.available_at = None
        await s.commit()
    assert await dispatch(data) == 1
    assert await dispatch(data) == 0 and data.send.await_count == 2
    assert cancel.await_count == 2
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        row = await s.get(WorkflowTriggerInbox, retry_id)
        assert row.processed_at and row.processing_error is None


async def test_legacy_booking_recovers_exact_run_and_calendar_link_at_clear_time(data, monkeypatch):
    from fusionflow.modules.connectors import service as connectors
    from fusionflow.modules.connectors.google_calendar.adapter import adapter
    run = await waiting(data, status=RunStatus.COMPLETED)
    record_id = await booking(data)  # Legacy rows have no creator run or event ID.
    calendar = uuid.uuid4()
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        version = await s.get(WorkflowVersion, data.versions[0])
        graph = {"nodes": [
            {"id": "calendar", "data": {"nodeType": "connector.action", "config": {"action": "create_event", "connector_instance_id": str(calendar)}}},
            {"id": "booking", "data": {"nodeType": "records.upsert", "config": {"module": "appointment", "operation": "create"}}},
        ], "edges": [{"source": "calendar", "target": "booking"}]}
        version.graph = version.compiled_graph = graph
        for node_id, output in [("calendar", {"id": "legacy-event"}), ("booking", {"item": {"id": str(record_id)}})]:
            s.add(WorkflowRunStep(tenant_id=data.tenants[0], workflow_run_id=run, node_id=node_id,
                node_type="test", status=StepStatus.SUCCEEDED, output=output))
        await s.commit()
    real_get = connectors.get_instance
    async def get_instance(s, *, tenant_id, instance_id):
        if instance_id == calendar:
            return SimpleNamespace(id=calendar, connector_type=SimpleNamespace(key="google_calendar"))
        return await real_get(s, tenant_id=tenant_id, instance_id=instance_id)
    monkeypatch.setattr(connectors, "get_instance", get_instance)
    cancel = AsyncMock()
    monkeypatch.setattr(adapter, "delete_event", cancel)
    await queue(data, "/clear", 1)
    assert await dispatch(data) == 2
    assert cancel.call_args.kwargs["event_id"] == "legacy-event"
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        assert await s.get(ObjectRecord, record_id) is None


async def test_quick_check_in_keeps_booking_customer_and_snapshots_name_and_phone(data):
    ref = await booking(data)
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        visit = await clinic.create_patient_visit(s, tenant_id=data.tenants[0], payload=PatientCreate(
            name="Actual Patient", phone="+919876543210", appointment_ref_id=ref))
        assert visit.customer_id == data.customers[0]
        customer = await s.get(Customer, data.customers[0])
        customer.name, customer.phone = "Later Family Member", "9999999999"
        result = clinic.to_patient_visit_out_dict(visit, customer=customer, doctor_name=None, include_notes=False)
        assert result["customer_name"] == "Actual Patient" and result["customer_phone"] == "+919876543210"
        assert "consultation_notes" not in result
        await s.commit()


async def test_check_in_rejects_other_tenant_or_cleared_booking(data):
    ref = await booking(data, tenant=1)
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        with pytest.raises(HTTPException) as error:
            await clinic.create_patient_visit(s, tenant_id=data.tenants[0], payload=PatientCreate(
                name="Patient", phone="1234567890", appointment_ref_id=ref))
        assert error.value.status_code == 409


@pytest.mark.parametrize("executor", [RecordUpsertExecutor, ModuleCreateExecutor])
async def test_workflow_custom_record_saves_creator_run(data, executor):
    run_id = await waiting(data, status=RunStatus.COMPLETED)
    await booking(data)  # Creates the tenant's appointment object type.
    async with data.factory() as s:
        await set_tenant_context(s, data.tenants[0])
        result = await executor().execute(ExecutionContext(session=s, tenant_id=data.tenants[0], run_id=run_id,
            node_id="create", config={"module": "appointment", "fields": {"customer_id": str(data.customers[0])}}, variables={}))
        assert isinstance(result, Success)
        record = await s.get(ObjectRecord, uuid.UUID(result.output["item"]["id"]))
        assert record.created_by_run_id == run_id and record.customer_id == data.customers[0]
