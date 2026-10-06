"""Remove a sender's active appointments; durably cancel their calendar events.

Appointment deletion and cancellation intent commit together. Only idempotent
calendar DELETEs are retried, never the Instagram acknowledgement or workflow.
"""
import asyncio
from datetime import datetime, timedelta, timezone
import logging
import uuid

from sqlalchemy import String, cast, select

from fusionflow.modules.business_objects.models import ObjectRecord, ObjectTypeDefinition
from fusionflow.modules.clinic_queue.models import PatientVisit, PatientVisitStage
from fusionflow.modules.customers.models import Customer
from fusionflow.modules.workflows.models import WorkflowRun, WorkflowTriggerInbox
from fusionflow.modules.workflows.engine.appointment_links import booking_evidence

logger = logging.getLogger(__name__)
CALENDAR_CANCEL_EVENT = "internal.appointment_calendar_cancel"
ACTIVE_BOOKING_STATUSES = ("draft", "requested", "confirmed")


async def clear_active_appointments(session, conversation) -> tuple[int, int]:
    from fusionflow.modules.workflows.engine.event_bus import publish_trigger_event

    source_runs = select(WorkflowRun.id).join(
        WorkflowTriggerInbox, WorkflowRun.trigger_event_ref == cast(WorkflowTriggerInbox.id, String),
    ).where(
        WorkflowRun.tenant_id == conversation.tenant_id,
        WorkflowTriggerInbox.tenant_id == conversation.tenant_id,
        WorkflowTriggerInbox.connector_instance_id == conversation.connector_instance_id,
        WorkflowTriggerInbox.event_type.in_(("instagram.message_received", "instagram.postback_received")),
        WorkflowTriggerInbox.payload["from"].astext == conversation.external_contact_id,
    )
    authorized_runs = set((await session.execute(source_runs)).scalars())
    appointments = (await session.execute(select(ObjectRecord).join(
        ObjectTypeDefinition, ObjectRecord.object_type_id == ObjectTypeDefinition.id,
    ).join(Customer, ObjectRecord.customer_id == Customer.id).where(
        ObjectRecord.tenant_id == conversation.tenant_id,
        ObjectTypeDefinition.tenant_id == conversation.tenant_id,
        ObjectTypeDefinition.key == "appointment",
        Customer.tenant_id == conversation.tenant_id,
        Customer.external_ref == conversation.external_contact_id,
        ObjectRecord.payload["status"].astext.in_(ACTIVE_BOOKING_STATUSES),
    ).with_for_update(of=ObjectRecord))).scalars().all()
    removed = queued = 0
    for record in appointments:
        if record.created_by_run_id not in authorized_runs or not record.payload.get("calendar_event_id"):
            evidence = await booking_evidence(session, record, sender=conversation.external_contact_id,
                                              connector_id=conversation.connector_instance_id)
            if evidence is not None:
                record.created_by_run_id, record.payload = evidence
        if record.created_by_run_id not in authorized_runs:
            continue  # Manual bookings and other channels cannot be erased by a DM.
        visits = (await session.execute(select(PatientVisit).where(
            PatientVisit.tenant_id == conversation.tenant_id,
            PatientVisit.appointment_ref_id == record.id,
        ).with_for_update())).scalars().all()
        # A completed clinical visit protects its booking even if an old
        # workflow left the appointment's status out of sync.
        if any(v.stage == PatientVisitStage.COMPLETED for v in visits):
            continue
        event_id = record.payload.get("calendar_event_id")
        connector_id = record.payload.get("calendar_connector_instance_id")
        if event_id and connector_id:
            await publish_trigger_event(
                session, tenant_id=conversation.tenant_id, event_type=CALENDAR_CANCEL_EVENT,
                connector_instance_id=uuid.UUID(connector_id),
                payload={"event_id": event_id, "appointment_id": str(record.id)},
                dedupe_key=f"appointment-clear:{record.id}",
            )
            queued += 1
        # Check-in/clinical notes are independent medical records. Retain
        # them and detach the deleted booking, rather than deleting care.
        for visit in visits:
            visit.appointment_ref_id = None
        await session.delete(record)
        removed += 1
    await session.flush()
    return removed, queued


def defer_calendar_cancellation(row, exc: Exception) -> None:
    attempts = int(row.payload.get("attempts", 0)) + 1
    row.payload = {**row.payload, "attempts": attempts}
    row.available_at = datetime.now(timezone.utc) + timedelta(seconds=min(60 * 2 ** min(attempts, 6), 3600))
    row.processing_error = f"{type(exc).__name__}; calendar cancellation pending"
    logger.warning("Calendar cancellation %s deferred (%s)", row.id, type(exc).__name__)


async def dispatch_calendar_cancellation(session, row) -> None:
    from fusionflow.modules.connectors import service
    from fusionflow.modules.connectors.google_calendar.adapter import adapter

    instance = await service.get_instance(session, tenant_id=row.tenant_id, instance_id=row.connector_instance_id)
    try:
        if instance is None or instance.connector_type.key != "google_calendar":
            raise ValueError("Calendar connection unavailable")
        # A calendar outage should not hold Instagram's dispatch lock for
        # a full provider timeout per booking.
        async with asyncio.timeout(5):
            await adapter.delete_event(instance, session, event_id=row.payload["event_id"])
    except Exception as exc:
        # Keep the intent and back off. A revoked token requires reconnect;
        # a future webhook/poller can finish without replaying any messages.
        defer_calendar_cancellation(row, exc)
    else:
        row.available_at = None
        row.processing_error = None
