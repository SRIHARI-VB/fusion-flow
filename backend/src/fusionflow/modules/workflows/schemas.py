from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from fusionflow.modules.workflows.models import (
    RunStatus,
    StepStatus,
    ValidationStatus,
    WorkflowStatus,
)

#: `Workflow.purpose` (recurring/bulk-messaging support) - which palette a
#: workflow's builder should show. Kept as a plain module-level tuple/
#: `Literal`, not `WorkflowStatus`-style `Enum` reuse, since `purpose` is a
#: plain `String` column on the model (see `models.py::Workflow.purpose`'s
#: docstring for why), not a DB-level enum.
WorkflowPurpose = Literal["automation", "broadcast"]


class WorkflowCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    graph: dict[str, Any] = Field(default_factory=lambda: {"nodes": [], "edges": []})
    # Composable-builder redesign (Phase 6): when set, `graph` above is
    # ignored and the new workflow's graph is seeded from the named
    # `WorkflowStarterTemplate` instead - see
    # `service.create_workflow_from_starter_template`.
    starter_template_id: uuid.UUID | None = None
    # Recurring/bulk-messaging support: "automation" (default, event-driven
    # triggers) or "broadcast" (`broadcast.scheduled_send` + a
    # `WorkflowSchedule`) - see `models.py::Workflow.purpose`'s docstring.
    purpose: WorkflowPurpose = "automation"
    # Advisory "which channel is this workflow for" tag - a `connector_types.key`
    # (e.g. "whatsapp", "instagram") or `None` for "General" (no specific
    # channel) - see `models.py::Workflow.channel_connector_type_key`'s
    # docstring. Chosen in the New Workflow wizard's new "channel" step.
    channel_connector_type_key: str | None = None


class WorkflowUpdateRequest(BaseModel):
    """PATCH body — partial update. Editing `graph` after the workflow has
    a published version creates a new draft `WorkflowVersion` rather than
    mutating the published one (see `service.get_draft_version`)."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    graph: dict[str, Any] | None = None


class BlockedModuleOut(BaseModel):
    key: str
    display_name: str
    reason: str  # 'denied' | 'not_requested' | 'pending'


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: WorkflowStatus
    purpose: str
    channel_connector_type_key: str | None
    current_published_version_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    # Computed at read time (router) from the published graph; never stored.
    blocked_modules: list[BlockedModuleOut] = Field(default_factory=list)


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
    # Recurring/bulk-messaging support: the set of `Workflow.purpose`
    # values this (trigger) entry is applicable under - `None` means
    # "applicable regardless of purpose" (every non-trigger entry, plus
    # `manual.test_trigger`). See `engine/registry.py`'s
    # `applicable_purposes` field docstring.
    applicable_purposes: list[str] | None = None


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
    # Auto-derived from the template's own graph (never hand-maintained -
    # see `admin.service.compute_required_connector_type_keys`) - purely
    # informational for a tenant deciding whether to use this template,
    # not a hard gate (unlike `WorkflowNodeTemplate.required_connector_type_key`,
    # which actually hides palette entries).
    required_connector_type_keys: list[str] = Field(default_factory=list)
    # Optional admin-authored free-text prerequisite guidance that isn't a
    # connector or custom-object-type dependency (e.g. "populate your
    # product catalog first").
    setup_notes: str | None = None
    # Server-computed from this template's own `graph_json` (its root
    # trigger's registered `applicable_purposes`) — see
    # `admin.service.compute_workflow_purpose`. `None` means "shown for
    # either 'automation' or 'broadcast'" (no single-purpose-exclusive
    # trigger tag resolved), not "unknown."
    purpose: str | None = None


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
    # Same auto-derived/informational semantics as
    # `WorkflowStarterTemplateSummaryOut.required_connector_type_keys` -
    # computed from `graph_fragment` itself, so this works identically for
    # both an admin-curated row and a tenant's own saved `source="user"`
    # component.
    required_connector_type_keys: list[str] = Field(default_factory=list)
    setup_notes: str | None = None


class WorkflowComponentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    category: str | None = Field(default=None, max_length=80)
    icon: str | None = Field(default=None, max_length=80)
    graph_fragment: dict[str, Any]


# --- Workflow schedules (recurring/bulk-messaging support) -----------------


class StaticRecipientSource(BaseModel):
    """`recipient_source.kind == "static"` - a hand-typed phone-number list,
    resolved at fire time exactly as given (see
    `engine/schedule_poller.py::_resolve_recipients`)."""

    kind: Literal["static"] = "static"
    phone_numbers: list[str] = Field(min_length=1)


class ModuleRecipientSource(BaseModel):
    """`recipient_source.kind == "module"` - resolved at fire time via a
    live query against a module (a fixed one, or a tenant's own custom
    object type), through the same `resolve_adapter`/`ModuleQueryAdapter.list`
    lookup `nodes/whatsapp_ask_choice.py`'s `ModuleSource` branch already
    uses at execute-time."""

    kind: Literal["module"] = "module"
    module: str = Field(min_length=1, description="A module key from GET /workflows/modules - fixed or custom.")
    filters: dict[str, Any] = Field(default_factory=dict)
    phone_field: str = Field(default="phone", description="Field on each matched row holding the recipient's phone number.")


RecipientSource = StaticRecipientSource | ModuleRecipientSource

#: "once" | "daily" | "weekly" | "monthly" - see `models.py::WorkflowSchedule`
#: and `compute_next_run_at`'s docstrings for the per-frequency field
#: requirements this module's validators below enforce.
ScheduleFrequency = Literal["once", "daily", "weekly", "monthly"]

_TIME_OF_DAY_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class WorkflowScheduleCreateRequest(BaseModel):
    frequency: ScheduleFrequency
    run_at: datetime | None = Field(default=None, description="Required (and only used) for frequency='once'.")
    time_of_day: str | None = Field(
        default=None, pattern=_TIME_OF_DAY_PATTERN, description="24h 'HH:MM', local to `timezone`."
    )
    weekdays: list[int] | None = Field(default=None, description="0=Monday..6=Sunday. Required for frequency='weekly'.")
    day_of_month: int | None = Field(default=None, ge=1, le=31, description="Required for frequency='monthly'.")
    timezone: str = Field(default="UTC", description="IANA tz name, e.g. 'UTC' or 'Asia/Kolkata'.")
    recipient_source: StaticRecipientSource | ModuleRecipientSource = Field(discriminator="kind")
    is_active: bool = True

    @model_validator(mode="after")
    def _check_frequency_fields(self) -> "WorkflowScheduleCreateRequest":
        if self.frequency == "once" and self.run_at is None:
            raise ValueError("run_at is required for a 'once' schedule")
        if self.frequency in ("daily", "weekly", "monthly") and not self.time_of_day:
            raise ValueError(f"time_of_day is required for a {self.frequency!r} schedule")
        if self.frequency == "weekly" and not self.weekdays:
            raise ValueError("weekdays is required for a 'weekly' schedule")
        if self.frequency == "monthly" and not self.day_of_month:
            raise ValueError("day_of_month is required for a 'monthly' schedule")
        return self


class WorkflowScheduleUpdateRequest(BaseModel):
    """PATCH body — partial update, including pause/resume via `is_active`.
    Every field optional; only fields the caller actually sent are applied
    (see `service.update_schedule`'s `exclude_unset` use)."""

    frequency: ScheduleFrequency | None = None
    run_at: datetime | None = None
    time_of_day: str | None = Field(default=None, pattern=_TIME_OF_DAY_PATTERN)
    weekdays: list[int] | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    timezone: str | None = None
    recipient_source: StaticRecipientSource | ModuleRecipientSource | None = Field(default=None, discriminator="kind")
    is_active: bool | None = None


class WorkflowScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workflow_id: uuid.UUID
    frequency: str
    run_at: datetime | None
    time_of_day: str | None
    weekdays: list[int] | None
    day_of_month: int | None
    timezone: str
    recipient_source: dict[str, Any]
    next_run_at: datetime
    is_active: bool
    last_run_at: datetime | None
    last_run_status: str | None
    created_at: datetime
    updated_at: datetime


class TriggerOverlapOut(BaseModel):
    """2+ published workflows that would both start a run for the same
    inbound event - see `service.get_trigger_overlaps`'s own docstring for
    why this is a real collision risk, not just a theoretical one."""

    trigger_type: str
    connector_instance_id: uuid.UUID | None
    workflow_names: list[str]
