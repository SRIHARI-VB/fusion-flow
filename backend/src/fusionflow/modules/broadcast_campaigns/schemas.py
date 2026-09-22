from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class BroadcastCampaignCreate(BaseModel):
    connector_instance_id: uuid.UUID
    name: str = Field(min_length=1, max_length=200)
    message_text: str = Field(min_length=1)
    # max_length=200 must match service.py::_build_graph's hard-coded
    # "max_iterations": 200 on the generated flow.loop node - without this
    # bound, a list longer than that silently gets truncated deep inside
    # `LoopExecutor.execute` (workflows/nodes/flow_loop.py) with no error,
    # so callers over the limit now get an immediate, clear 422 instead of
    # a partially-sent campaign that still reports 201 Created.
    recipient_phone_numbers: list[str] = Field(min_length=1, max_length=200)
    scheduled_at: datetime
    # Optional media attachment, sent as its own message ahead of
    # `message_text` - `None` (default) is the original text-only behavior.
    media_url: str | None = Field(default=None)
    media_type: str | None = Field(default=None)
    # Optional location attachment - WhatsApp only (Instagram's Send API
    # has no location-message capability); `service.create_campaign`
    # rejects this for an Instagram connector instance. Latitude/longitude
    # are a hard technical requirement and enforced as a pair below (Meta's
    # location-message API needs both or neither); `name`/`address` are
    # genuinely optional extra detail on top of a valid coordinate pair and
    # may be set independently. `None` (default) for all four is the
    # original, unset behavior.
    location_latitude: float | None = Field(default=None)
    location_longitude: float | None = Field(default=None)
    location_name: str | None = Field(default=None)
    location_address: str | None = Field(default=None)

    @model_validator(mode="after")
    def _validate_location_pair(self) -> "BroadcastCampaignCreate":
        if (self.location_latitude is None) != (self.location_longitude is None):
            raise ValueError("location_latitude and location_longitude must both be set or both be omitted")
        return self


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
