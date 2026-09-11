"""Workflow engine models (plan M5): workflows, immutable published
versions, runs, run steps, the denormalized trigger index, and the
trigger inbox (transactional outbox).

All six tables are tenant-scoped (`TenantScopedMixin`) and need
`fusionflow.db.rls.enable_tenant_rls(op, "<table>")` in their migration,
same as every other tenant table in this codebase.

NOT wired into `fusionflow.db.models` (the single ORM import point) or
`fusionflow.api` by this module — see the workflows agent's handoff notes
for the exact lines to add there.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fusionflow.db.base import Base, TenantScopedMixin, TimestampMixin


class WorkflowStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ValidationStatus(str, enum.Enum):
    VALID = "valid"
    INVALID = "invalid"


class RunStatus(str, enum.Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # Phase 8 Part A: the run is paused mid-graph at `waiting_node_id`,
    # waiting for a specific customer's next inbound message
    # (`waiting_correlation_key`, e.g. a phone number) on a specific
    # connector instance - see run_loop.py's `RunSuspended`/`resume_run`.
    WAITING = "waiting"


class StepStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class Workflow(Base, TenantScopedMixin, TimestampMixin):
    __tablename__ = "workflows"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[WorkflowStatus] = mapped_column(
        Enum(WorkflowStatus, name="workflow_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=WorkflowStatus.DRAFT,
        server_default=WorkflowStatus.DRAFT.value,
    )
    # `workflow_versions.workflow_id` FKs back to this table, so this
    # column and that one point at each other. A migration must create
    # both tables before adding this FK (`use_alter=True` tells Alembic
    # autogenerate to emit it as a separate ALTER TABLE, not inline).
    current_published_version_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey(
            "workflow_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_workflows_current_published_version",
        ),
        nullable=True,
    )

    versions: Mapped[list["WorkflowVersion"]] = relationship(
        back_populates="workflow",
        foreign_keys="WorkflowVersion.workflow_id",
        cascade="all, delete-orphan",
    )


class WorkflowVersion(Base, TenantScopedMixin, TimestampMixin):
    """Immutable once published — `publish_workflow` sets `published_at`
    and never mutates `graph` again; a further edit creates a new draft
    version instead (see `service.get_draft_version`)."""

    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint("workflow_id", "version_number", name="uq_workflow_version_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # The *authored* graph - may reference `WorkflowNodeTemplate` keys as
    # a node's `data.nodeType`, not just raw registered node types. Never
    # rewritten by publish, so editing a published workflow still shows
    # the friendly template identity instead of what it compiles to.
    graph: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # The *compiled* graph - every template-backed node resolved to its
    # real `base_node_type` + merged config (see `engine.
    # template_resolution.resolve_node_templates`). Set only on publish;
    # `null` for a draft version. This, not `graph`, is what the run loop
    # actually executes (`outbox_poller.py`) - the engine never needs to
    # know templates exist.
    compiled_graph: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    validation_status: Mapped[ValidationStatus | None] = mapped_column(
        Enum(
            ValidationStatus,
            name="workflow_validation_status",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    validation_errors: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    workflow: Mapped[Workflow] = relationship(back_populates="versions", foreign_keys=[workflow_id])


class WorkflowRun(Base, TenantScopedMixin):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        # Phase 8 Part A: at most one paused conversation per customer per
        # channel at a time - a second inbound message from the same
        # customer while one run is already waiting always resumes that
        # same run (see event_bus.find_pending_wait), never starts a
        # second one. Partial (only enforced while status='waiting'),
        # mirroring WorkflowTriggerInbox's own partial-unique-index
        # pattern above.
        Index(
            "uq_workflow_runs_waiting_correlation",
            "tenant_id",
            "waiting_connector_instance_id",
            "waiting_correlation_key",
            unique=True,
            postgresql_where=text("status = 'waiting'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workflow_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Free-text reference (e.g. a `workflow_trigger_inbox.id` or
    # "simulate") — not an FK, so a run's provenance survives the inbox
    # row eventually being pruned.
    trigger_event_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[RunStatus] = mapped_column(
        Enum(RunStatus, name="workflow_run_status", values_callable=lambda e: [m.value for m in e]),
        nullable=False,
        default=RunStatus.RUNNING,
        server_default=RunStatus.RUNNING.value,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The runtime safety backstop (plan Risk #7): incremented per executed
    # step by the run loop; exceeding WORKFLOW_LOOP_GUARD_MAX force-fails
    # the run, independent of and in addition to publish-time static
    # cycle analysis.
    loop_guard_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    # Phase 8 Part A: suspended-run state, populated only while
    # `status == WAITING` (cleared back to NULL on resume, see
    # run_loop.py::resume_run). A run has at most one active pause at a
    # time, so this lives directly on the row instead of a new table.
    waiting_node_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # No FK: `connector_instances` lives in a different module built in a
    # parallel wave, same reasoning as `WorkflowTrigger.connector_instance_id`.
    waiting_connector_instance_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), nullable=True
    )
    waiting_correlation_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    waiting_frontier: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    waiting_variables: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    waiting_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["WorkflowRunStep"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="WorkflowRunStep.started_at",
    )


class WorkflowRunStep(Base, TenantScopedMixin):
    __tablename__ = "workflow_run_steps"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Graph node id (JSONB `nodes[].id`), not an FK — nodes live inside the
    # version's `graph` JSONB, not as their own rows.
    node_id: Mapped[str] = mapped_column(String(100), nullable=False)
    node_type: Mapped[str] = mapped_column(String(150), nullable=False)
    status: Mapped[StepStatus] = mapped_column(
        Enum(
            StepStatus, name="workflow_run_step_status", values_callable=lambda e: [m.value for m in e]
        ),
        nullable=False,
        default=StepStatus.PENDING,
        server_default=StepStatus.PENDING.value,
    )
    input: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")

    run: Mapped[WorkflowRun] = relationship(back_populates="steps")


class WorkflowTrigger(Base, TenantScopedMixin, TimestampMixin):
    """Denormalized index rebuilt on every successful publish (see
    `service._rebuild_triggers`) for O(1) inbox dispatch — the outbox
    poller matches inbox rows against this table, never against a live
    graph walk."""

    __tablename__ = "workflow_triggers"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger_type: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    # No FK: `connector_instances` lives in a different module (built in a
    # parallel wave) and may not exist in every deployment/test build.
    # Validated in application code (validation.py rule 2), not the DB.
    connector_instance_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class WorkflowTriggerInbox(Base, TenantScopedMixin):
    """Transactional outbox row. Written by `engine.event_bus.publish_trigger_event`
    in the *same* transaction as the triggering domain write (a webhook
    handler, an `order.created` mutation, ...), so a crash before commit
    loses both writes together and a crash after commit has durably
    recorded both — no lost trigger events."""

    __tablename__ = "workflow_trigger_inbox"
    __table_args__ = (
        Index(
            "uq_workflow_trigger_inbox_tenant_dedupe_key",
            "tenant_id",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    connector_instance_id: Mapped[uuid.UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    # A provider-supplied delivery/event id (e.g. a webhook's own event id),
    # when the caller has one - lets `publish_trigger_event` detect a
    # redelivered webhook and skip creating a second inbox row (and thus a
    # second `WorkflowRun`) for it. Null for callers with no natural
    # dedupe key (e.g. `order.created`, which is a one-shot domain write,
    # not a redeliverable webhook) - the partial unique index only applies
    # when set.
    dedupe_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WorkflowUserComponent(Base, TenantScopedMixin, TimestampMixin):
    """A tenant's own reusable workflow fragment - the "save this selection
    of nodes as a component" sibling of the admin-curated
    `modules.admin.models.WorkflowComponent` catalog. Both are merged into
    one list by `service.list_components`, distinguished there by a
    `source: "admin" | "user"` tag rather than by table.

    `graph_fragment` is built client-side from whatever nodes+edges the
    tenant currently has selected on their canvas (see
    `WorkflowEditorPage.tsx`'s "Save as Component" action) - the same
    `{"nodes": [...], "edges": [...]}` shape a full workflow graph uses,
    stripped of client-only fields (`__meta`, etc.) the same way
    `graphUtils.toGraphJson` already strips them before a workflow save.
    """

    __tablename__ = "workflow_user_components"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True, default="Custom")
    icon: Mapped[str | None] = mapped_column(String(80), nullable=True)
    graph_fragment: Mapped[dict] = mapped_column(JSONB, nullable=False)
