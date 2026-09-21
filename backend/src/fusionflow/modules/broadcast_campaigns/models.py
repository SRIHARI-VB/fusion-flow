"""`BroadcastCampaign`: the tenant-facing record for one scheduled bulk
send. Deliberately thin, same rationale as
`predefined_automations.models.PredefinedAutomation`: the actual send
logic is an ordinary `Workflow` (a `broadcast.scheduled_send` trigger ->
`flow.loop` over the recipient list -> `connector.action` send) plus the
`WorkflowSchedule` row that fires it - this table exists only so the
frontend has a "campaign" to list/pause/delete without ever touching the
canvas, and so the tenant-entered fields (name, message text, recipient
list) survive independently of the generated graph for re-editing.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class BroadcastCampaign(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "broadcast_campaigns"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connector_instance_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("connector_instances.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    # Hand-typed recipient list - same phase-1 scope as
    # `WorkflowSchedule.recipient_source`'s "static" kind, which this
    # campaign's generated schedule always uses (no live-module-query
    # campaigns yet; a tenant with a fixed-module contact list can already
    # reach that richer path directly via the generic `/workflows` API).
    recipient_phone_numbers: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_schedules.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
