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
    # Optional media attachment, sent as its own message ahead of
    # `message_text` - `None` (default) is the original text-only behavior.
    media_url: str | None = Field(default=None)
    media_type: str | None = Field(default=None)
    # Optional location attachment - WhatsApp only (Instagram's Send API
    # has no location-message capability); `service.create_campaign`
    # rejects this for an Instagram connector instance. All four are set
    # together or not at all - `None` (default) is the original behavior.
    location_latitude: float | None = Field(default=None)
    location_longitude: float | None = Field(default=None)
    location_name: str | None = Field(default=None)
    location_address: str | None = Field(default=None)


class BroadcastCampaignSetActive(BaseModel):
    is_active: bool


class BroadcastCampaignOut(BaseModel):
    id: uuid.UUID
    connector_instance_id: uuid.UUID
    name: str
    message_text: str
    recipient_phone_numbers: list[str]
    media_url: str | None
    media_type: str | None
    location_latitude: float | None
    location_longitude: float | None
    location_name: str | None
    location_address: str | None
    workflow_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    # Read off the underlying `WorkflowSchedule`, not duplicated on
    # `BroadcastCampaign` itself - see `service.get_schedule_for_campaign`.
    next_run_at: datetime | None
    is_active: bool
    last_run_at: datetime | None
    last_run_status: str | None
