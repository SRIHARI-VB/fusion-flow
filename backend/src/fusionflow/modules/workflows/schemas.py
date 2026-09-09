from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.workflows.models import (
    RunStatus,
    StepStatus,
    ValidationStatus,
    WorkflowStatus,
)


class WorkflowCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    graph: dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})


class WorkflowUpdateRequest(BaseModel):
    """PATCH body — partial update. Editing `graph` after the workflow has
    a published version creates a new draft `WorkflowVersion` rather than
    mutating the published one (see `service.get_draft_version`)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    graph: dict[str, Any] | None = None


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: WorkflowStatus
    current_published_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class WorkflowVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    version_number: int
    graph: dict[str, Any]
    validation_status: ValidationStatus | None
    validation_errors: list[dict[str, Any]] | None
    published_at: datetime | None
    created_by: uuid.UUID | None
    created_at: datetime


class PublishResponse(BaseModel):
    workflow: WorkflowOut
    version: WorkflowVersionOut
    valid: bool
    issues: list[dict[str, Any]]


class SimulateRequest(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class RunStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    node_id: str
    node_type: str
    status: StepStatus
    input: dict[str, Any] | None
    output: dict[str, Any] | None
    error: str | None
    started_at: datetime | None
    completed_at: datetime | None
    attempt: int


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    workflow_version_id: uuid.UUID
    trigger_event_ref: str | None
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None
    loop_guard_count: int


class RunDetailOut(RunOut):
    steps: list[RunStepOut] = Field(default_factory=list)


class NodeTypeOut(BaseModel):
    node_type: str
    kind: str
    category: str
    label: str
    description: str
    config_schema: dict[str, Any]
    output_handles: list[str] | None = None
