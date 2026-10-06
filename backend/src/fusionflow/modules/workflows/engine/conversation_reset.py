"""Instagram /clear, processed in inbox order before any resume decision.

The dispatcher owns the transaction and serializes dispatch for the tenant.
Patient, ticket, completed appointment and message history are preserved.
Active appointments are removed with durable calendar cancellation intents.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import uuid

from sqlalchemy import String, cast, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.business_objects.models import ObjectRecord, ObjectTypeDefinition
from fusionflow.modules.customers.models import Customer
from fusionflow.modules.inbox.models import Conversation
from fusionflow.modules.workflows.models import RunStatus, WorkflowRun, WorkflowTriggerInbox
from fusionflow.modules.workflows.engine.appointment_reset import clear_active_appointments

logger = logging.getLogger(__name__)
INSTAGRAM_EVENTS = {"instagram.message_received", "instagram.postback_received"}
RESET_ACK = "Your current conversation has been reset. Send Hi to start again."


def is_clear_command(payload: dict) -> bool:
    value = payload.get("text")
    return isinstance(value, str) and value.strip().casefold() == "/clear"


def event_time(row: WorkflowTriggerInbox) -> datetime:
    """Meta's original timestamp survives redelivery; old rows use receipt time."""
    value = row.payload.get("timestamp")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        try:
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            pass
    return row.created_at


async def cancel_conversation_runs(session: AsyncSession, conversation: Conversation) -> None:
    source_events = select(cast(WorkflowTriggerInbox.id, String)).where(
        WorkflowTriggerInbox.tenant_id == conversation.tenant_id,
        WorkflowTriggerInbox.connector_instance_id == conversation.connector_instance_id,
        WorkflowTriggerInbox.payload["from"].astext == conversation.external_contact_id,
    )
    runs = (await session.execute(select(WorkflowRun).where(
        WorkflowRun.tenant_id == conversation.tenant_id,
        WorkflowRun.status.in_([RunStatus.RUNNING, RunStatus.WAITING]),
        or_(
            (WorkflowRun.waiting_connector_instance_id == conversation.connector_instance_id)
            & (WorkflowRun.waiting_correlation_key == conversation.external_contact_id),
            WorkflowRun.trigger_event_ref.in_(source_events),
        ),
    ).with_for_update())).scalars().all()
    for run in runs:
        run.status = RunStatus.CANCELLED
        run.completed_at = datetime.now(timezone.utc)
        for field in ("waiting_node_id", "waiting_connector_instance_id", "waiting_correlation_key",
                      "waiting_frontier", "waiting_variables", "waiting_expires_at"):
            setattr(run, field, None)
    if runs:
        customer_ids = select(Customer.id).where(
            Customer.tenant_id == conversation.tenant_id,
            Customer.external_ref == conversation.external_contact_id,
        )
        await session.execute(delete(ObjectRecord).where(
            ObjectRecord.tenant_id == conversation.tenant_id,
            ObjectRecord.customer_id.in_(customer_ids),
            ObjectRecord.created_by_run_id.in_([run.id for run in runs]),
            ObjectRecord.payload["status"].astext == "draft",
            ObjectRecord.object_type_id.not_in(select(ObjectTypeDefinition.id).where(
                ObjectTypeDefinition.tenant_id == conversation.tenant_id,
                ObjectTypeDefinition.key == "appointment",
            )),
        ))
    await session.flush()


@dataclass
class ResetDispatch:
    handled: bool = False
    conversation: Conversation | None = None


async def prepare_instagram_event(session: AsyncSession, row: WorkflowTriggerInbox) -> ResetDispatch:
    sender = row.payload.get("from")
    if not sender or row.connector_instance_id is None:
        return ResetDispatch()
    conversation = (await session.execute(select(Conversation).where(
        Conversation.tenant_id == row.tenant_id,
        Conversation.connector_instance_id == row.connector_instance_id,
        Conversation.external_contact_id == sender,
    ).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if conversation is not None and conversation.flow_reset_at is not None:
        if event_time(row) <= conversation.flow_reset_at:
            return ResetDispatch(handled=True, conversation=conversation)

    if row.event_type == "instagram.message_received" and is_clear_command(row.payload):
        if conversation is None:
            conversation = Conversation(
                id=uuid.uuid4(), tenant_id=row.tenant_id,
                connector_instance_id=row.connector_instance_id, external_contact_id=sender,
                unread_count=0,
            )
            session.add(conversation)
        await cancel_conversation_runs(session, conversation)
        removed, calendar_pending = await clear_active_appointments(session, conversation)
        conversation.flow_reset_at = event_time(row)
        conversation.flow_reset_pending = True
        # An explicit restart also releases a prior human-handoff pause.
        conversation.automation_paused = False
        conversation.automation_paused_until = None
        await session.flush()

        from fusionflow.modules.connectors import service as connector_service
        from fusionflow.modules.connectors.base import registry

        instance = await connector_service.get_instance(
            session, tenant_id=row.tenant_id, instance_id=row.connector_instance_id,
        )
        try:
            if instance is None:
                raise ValueError("Reset acknowledgement connector is missing")
            acknowledgement = RESET_ACK
            if removed:
                acknowledgement = (
                    f"Your conversation has been reset and {removed} active booking(s) removed. "
                    "Send Hi to start again."
                )
                if calendar_pending:
                    acknowledgement += " Calendar cancellations have been queued for syncing."
            await registry.get("instagram").perform_action(
                action="send_direct_message", params={"recipient_id": sender, "text": acknowledgement},
                instance=instance, session=session,
            )
        except Exception:
            # A provider outage must not undo the user's reset. The next
            # message will still start fresh even if this acknowledgement fails.
            logger.warning("Could not acknowledge conversation reset for inbox row %s", row.id, exc_info=True)
        return ResetDispatch(handled=True, conversation=conversation)

    if conversation is not None and conversation.flow_reset_pending:
        if row.event_type == "instagram.postback_received":
            # Until a fresh message starts the flow, old menu taps have no
            # conversation state to act upon and must not consume the marker.
            return ResetDispatch(handled=True, conversation=conversation)
        row.payload = {**row.payload, "conversation_reset": True}
    return ResetDispatch(conversation=conversation)
