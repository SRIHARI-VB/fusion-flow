"""Broadcast-campaign domain logic.

Generated graph shape: trigger (`broadcast.scheduled_send`, seeds
`trigger.recipients` from the schedule's `recipient_source` at fire time -
see `workflows/nodes/broadcast_scheduled_send.py`) -> `flow.loop` (iterates
`trigger.recipients`, one phone number per iteration as `loop.item`) ->
one `connector.action` child (`parentId` set to the loop node's id - see
`engine/graph.py::GraphNode.parent_id` - `send_text_message` with
`to: "{{loop.item}}"`). No edge is needed from the loop to its one child:
container membership is established by `parent_id` alone
(`validation.py::_check_containment_validity`); an edge is only needed
among SIBLINGS to order them, and there is only one child here.

Same "ordinary `Workflow` + a service-owned wrapper row" pattern as
`predefined_automations.service` - reuses `workflows_service.create_workflow`/
`publish_workflow` unchanged, plus (new here) `workflows_service.
create_schedule`/`update_schedule` for the one-off `WorkflowSchedule` that
actually fires the send. Every function using this codebase's standard
"the router owns the transaction boundary" convention (no commits here).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.broadcast_campaigns.models import BroadcastCampaign
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.schemas import StaticRecipientSource, WorkflowScheduleCreateRequest, WorkflowScheduleUpdateRequest


class BroadcastCampaignError(Exception):
    """Domain-level failure. `status_code` is the HTTP status to emit -
    matches `connectors.service.ConnectorError`'s identical shape."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _build_graph(*, connector_instance_id: uuid.UUID, message_text: str) -> dict:
    instance_id = str(connector_instance_id)
    return {
        "nodes": [
            {
                "id": "trigger",
                "type": "trigger",
                "position": {"x": 0, "y": 0},
                "data": {"nodeType": "broadcast.scheduled_send", "label": "Scheduled Send", "config": {}},
            },
            {
                "id": "loop",
                "type": "action",
                "position": {"x": 260, "y": 0},
                "data": {
                    "nodeType": "flow.loop",
                    "label": "For Each Recipient",
                    "config": {"items_path": "{{trigger.recipients}}", "max_iterations": 200},
                },
            },
            {
                "id": "send",
                "type": "action",
                "position": {"x": 260, "y": 120},
                "parentId": "loop",
                "data": {
                    "nodeType": "connector.action",
                    "label": "Send Message",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "send_text_message",
                        "params": {"to": "{{loop.item}}", "body": message_text},
                    },
                },
            },
        ],
        "edges": [{"id": "e-trigger-loop", "source": "trigger", "target": "loop"}],
    }


async def _get_whatsapp_instance_or_raise(session: AsyncSession, *, tenant_id: uuid.UUID, connector_instance_id: uuid.UUID):
    instance = await connector_service.get_instance(session, tenant_id=tenant_id, instance_id=connector_instance_id)
    if instance is None:
        raise BroadcastCampaignError(404, "Connector instance not found")
    if instance.connector_type.key != "whatsapp":
        raise BroadcastCampaignError(
            400, f"Broadcast campaigns require a WhatsApp connector instance, not {instance.connector_type.key!r}"
        )
    return instance


async def create_campaign(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connector_instance_id: uuid.UUID,
    name: str,
    message_text: str,
    recipient_phone_numbers: list[str],
    scheduled_at: datetime,
    created_by: uuid.UUID,
) -> BroadcastCampaign:
    await _get_whatsapp_instance_or_raise(session, tenant_id=tenant_id, connector_instance_id=connector_instance_id)

    graph = _build_graph(connector_instance_id=connector_instance_id, message_text=message_text)
    workflow = await workflows_service.create_workflow(
        session, tenant_id=tenant_id, name=name, graph=graph, created_by=created_by, purpose="broadcast"
    )
    _, _, result = await workflows_service.publish_workflow(session, workflow, published_by=created_by)
    if result.has_errors:
        raise BroadcastCampaignError(422, f"Generated campaign failed validation: {result.to_json()}")

    schedule = await workflows_service.create_schedule(
        session,
        tenant_id=tenant_id,
        workflow_id=workflow.id,
        payload=WorkflowScheduleCreateRequest(
            frequency="once",
            run_at=scheduled_at,
            recipient_source=StaticRecipientSource(phone_numbers=recipient_phone_numbers),
            is_active=True,
        ),
    )

    campaign = BroadcastCampaign(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_instance_id=connector_instance_id,
        name=name,
        message_text=message_text,
        recipient_phone_numbers=recipient_phone_numbers,
        workflow_id=workflow.id,
        schedule_id=schedule.id,
    )
    session.add(campaign)
    await session.flush()
    return campaign


async def list_campaigns(session: AsyncSession, *, tenant_id: uuid.UUID) -> Sequence[BroadcastCampaign]:
    stmt = (
        select(BroadcastCampaign)
        .where(BroadcastCampaign.tenant_id == tenant_id)
        .order_by(BroadcastCampaign.created_at.desc())
    )
    return (await session.execute(stmt)).scalars().all()


async def get_campaign(session: AsyncSession, *, tenant_id: uuid.UUID, campaign_id: uuid.UUID) -> BroadcastCampaign | None:
    return (
        await session.execute(
            select(BroadcastCampaign).where(
                BroadcastCampaign.id == campaign_id, BroadcastCampaign.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()


async def get_schedule_for_campaign(session: AsyncSession, campaign: BroadcastCampaign):
    """The campaign's own `WorkflowSchedule` row - callers (the router's
    `to_out` mapper) read `next_run_at`/`is_active`/`last_run_status` off
    it rather than this table duplicating any of that state."""
    return await workflows_service.get_schedule(session, campaign.schedule_id)


async def set_active(session: AsyncSession, campaign: BroadcastCampaign, *, is_active: bool) -> BroadcastCampaign:
    """Pause/resume - unlike a predefined automation's pause (which tears
    down `workflow_triggers`, since domain-event triggers dispatch off
    that table), a schedule-driven campaign is paused far more simply:
    `WorkflowSchedule.is_active=False` is exactly what `schedule_poller.
    poll_once` already checks before ever firing a due row - no workflow-
    level status change needed at all."""
    schedule = await workflows_service.get_schedule(session, campaign.schedule_id)
    if schedule is None:
        raise BroadcastCampaignError(404, "Underlying schedule not found")
    await workflows_service.update_schedule(session, schedule, payload=WorkflowScheduleUpdateRequest(is_active=is_active))
    return campaign


async def delete_campaign(session: AsyncSession, campaign: BroadcastCampaign) -> None:
    """Deletes the campaign row plus its `Workflow` (which cascades to the
    `WorkflowSchedule`, `WorkflowVersion`s, and any `WorkflowRun`s) -
    `workflow_schedules.workflow_id` has `ondelete="CASCADE"` (see that
    model), so deleting the workflow is sufficient; no separate schedule
    delete needed."""
    workflow = await workflows_service.get_workflow(session, campaign.workflow_id)
    await session.delete(campaign)
    if workflow is not None:
        await workflows_service.delete_workflow(session, workflow)
