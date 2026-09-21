from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class BroadcastCampaignCreate(BaseModel):
    connector_instance_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    message_text: str = Field(min_length=1)
    recipient_phone_numbers: list[str] = Field(min_length=1)
    scheduled_at: datetime


class BroadcastCampaignSetActive(BaseModel):
    is_active: bool


class BroadcastCampaignOut(BaseModel):
    id: uuid.UUID
    connector_instance_id: uuid.UUID
    name: str
    message_text: str
    recipient_phone_numbers: list[str]
    workflow_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Read off the underlying `WorkflowSchedule`, not duplicated on
    # `BroadcastCampaign` itself - see `service.get_schedule_for_campaign`.
    next_run_at: datetime | None
    is_active: bool
    last_run_at: datetime | None
    last_run_status: str | None
