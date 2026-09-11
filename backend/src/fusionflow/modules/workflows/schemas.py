from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

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
    # Composable-builder redesign (Phase 6): when set, `graph` above is
    # ignored and the new workflow's graph is seeded from the named
    # `WorkflowStarterTemplate` instead - see
    # `service.create_workflow_from_starter_template`.
    starter_template_id: uuid.UUID | None = None


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
    subcategory: str | None = None
    label: str
    description: str
    config_schema: dict[str, Any]
    output_handles: list[str] | None = None
    optional_output_handles: list[str] | None = None
    can_contain_children: bool = False
    child_role: str | None = None
    # Set only for a `WorkflowNodeTemplate`-backed palette entry (see
    # modules.admin.models.WorkflowNodeTemplate) - the config a newly
    # dropped node of this type should be pre-filled with. Empty for a
    # raw registered node type, which has no per-instance defaults.
    default_config: dict[str, Any] = Field(default_factory=dict)
    # Present only on a template-backed entry - the underlying registered
    # node type this one resolves to at publish time (see engine.
    # template_resolution). `None` for a raw registered node type (where
    # `node_type` already *is* the base type).
    base_node_type: str | None = None
    # Phase 7 Part A: the `connector_types.key` a tenant must have "granted"
    # access to for this entry to appear at all - `service.list_node_types_with_templates`
    # drops any entry that fails this check before the response is built, so
    # by the time this reaches the client it's informational only (the
    # frontend derives "is this channel currently allowed" from presence in
    # this already-filtered list, not from re-checking this field itself).
    required_connector_type_key: str | None = None
    # Phase 7 Part B: declared shape of this node type's `Success.output`,
    # same JSON-Schema-lite shape `config_schema` uses - powers the
    # "insert a variable from an earlier step" picker. None for node types
    # not yet catalogued (see registry.NodeTypeMeta's docstring).
    output_schema: dict[str, Any] | None = None
    # Phase 7 Part C: tenant-specific dropdown options for select config
    # fields (today: "connector_instance_id" and "module"), computed fresh
    # per request inside `service.list_node_types_with_templates` - never a
    # static node-type attribute, unlike everything else on this model.
    field_suggestions: dict[str, list[dict[str, str]]] | None = None
    # Composable-builder redesign (see engine.registry.NodeTypeMeta's
    # docstrings): a lucide-react icon key for the palette card, and the
    # task-oriented palette bucket this entry shows under by default.
    # `palette_group` is never None by the time it reaches this schema -
    # `service._default_palette_group` fills in a sensible bucket for any
    # node type that doesn't declare one explicitly.
    icon: str | None = None
    palette_group: str = "Advanced"


class ModuleFieldOut(BaseModel):
    """One field a `records.query`/`records.upsert` node's `fields`/
    `filters` config can target - the same flat shape whether it came from
    a fixed module's `*Create` schema, a tenant's `custom_fields.
    FieldDefinition` row, or a tenant's own `business_objects.
    ObjectFieldDefinition` row (see `module_catalog.py`)."""

    key: str
    label: str
    field_type: str
    options: list[Any] | None = None
    required: bool = False


class WorkflowStarterTemplateSummaryOut(BaseModel):
    """Tenant-facing view of one `admin.models.WorkflowStarterTemplate` row
    (`GET /workflows/starter-templates`) - just enough for a "start from a
    template" picker card. The full row (`graph_json`/`required_object_types`)
    stays server-side; see `service.create_workflow_from_starter_template`."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    description: str | None = None
    category: str
    icon: str | None = None


class ModuleCatalogEntryOut(BaseModel):
    """One entry in the unified module picker (`GET /workflows/modules`):
    a fixed module (Products, Orders, ...) or one of this tenant's own
    custom object types (Delivery, Appointment, ...) - the same shape
    either way, per the plan's "one picker" decision."""

    key: str
    label: str
    icon: str | None = None
    category: str
    source: Literal["fixed", "custom"]
    supported_operations: list[str]
    fields: list[ModuleFieldOut]


class WorkflowComponentOut(BaseModel):
    """One entry in the unified component picker (`GET /workflows/components`):
    an admin-curated `admin.models.WorkflowComponent` row or one of this
    tenant's own saved `models.WorkflowUserComponent` rows - the same shape
    either way, distinguished by `source`, mirroring `ModuleCatalogEntryOut`'s
    "one merged list" pattern.

    Unlike `WorkflowStarterTemplateSummaryOut` (which deliberately omits
    `graph_json` - a starter template is only ever instantiated server-side),
    `graph_fragment` IS included here: a component is merged into the
    canvas *client-side* by `WorkflowEditorPage.tsx` (fresh node ids,
    positioned near the current viewport), so the frontend genuinely needs
    the raw fragment, not just catalog metadata.
    """

    id: str
    name: str
    description: str | None = None
    category: str | None = None
    icon: str | None = None
    source: Literal["admin", "user"]
    graph_fragment: dict[str, Any]
    required_object_types: list[dict[str, Any]] | None = None


class WorkflowComponentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    icon: str | None = Field(default=None, max_length=80)
    graph_fragment: dict[str, Any]
