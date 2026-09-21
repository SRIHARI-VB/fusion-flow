from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PredefinedAutomationCreate(BaseModel):
    connector_instance_id: uuid.UUID
    automation_type: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    config: dict[str, Any] = Field(default_factory=dict)


class PredefinedAutomationUpdate(BaseModel):
    """Partial update - only `config` is ever edited (the wizard reopens
    with the stored `config`, never the generated graph); `automation_type`/
    `connector_instance_id` are immutable after creation, same
    "delete and recreate to change shape" convention as
    `custom_fields.schemas.FieldDefinitionUpdate`."""

    config: dict[str, Any]


class PredefinedAutomationSetActive(BaseModel):
    is_active: bool


class PredefinedAutomationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_instance_id: uuid.UUID
    automation_type: str
    workflow_id: uuid.UUID
    config: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class PredefinedAutomationTypeOut(BaseModel):
    """One entry of the registry catalog - `GET /predefined-automations/types`."""

    automation_type: str
    connector_type_key: str
    label: str
    description: str
