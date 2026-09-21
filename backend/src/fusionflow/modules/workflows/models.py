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

import calendar
import enum
import uuid
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from sqlalchemy import (
    Boolean,
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
    # Recurring/scheduled bulk-messaging support: which palette a workflow's
    # builder should show - "automation" (event-driven triggers, the
    # pre-existing default) or "broadcast" (`broadcast.scheduled_send` +
    # a `WorkflowSchedule` row). Plain string, not a DB `Enum`, matching
    # this column's own "just two values, no migration ceremony to add a
    # third" simplicity - see `engine/registry.py`'s `applicable_purposes`
    # and `service.list_node_types_with_templates`'s purpose filter, which
    # is the only place this value is actually interpreted.
    purpose: Mapped[str] = mapped_column(
        String(20), nullable=False, default="automation", server_default="automation"
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


class WorkflowSchedule(Base, TenantScopedMixin, TimestampMixin):
    """Recurring/scheduled bulk-send config for a `broadcast.scheduled_send`
    -triggered workflow (recurring/bulk-messaging support).

    `engine/schedule_poller.py` polls `next_run_at` (indexed) across every
    tenant — the same cross-tenant iteration pattern `engine/outbox_poller.py`
    already uses — and, for each due & active row, resolves `recipient_source`
    (a static phone-number list, or a live query against a module) into a
    concrete recipient list and starts one `WorkflowRun` with
    `trigger_payload={"recipients": [...]}`, exactly like the outbox poller
    starts a run per matched inbox row (see that file's `_start_run_for_trigger`).

    `recipient_source` is plain JSONB here (not a Pydantic model on the ORM
    side) — its `{"kind": "static"|"module", ...}` discriminated shape is
    validated at the Pydantic-schema layer (`schemas.py`'s
    `StaticRecipientSource`/`ModuleRecipientSource`), mirroring
    `nodes/whatsapp_ask_choice.py`'s `StaticSource`/`ModuleSource` pattern
    conceptually, not literally (that one IS a Pydantic model, embedded in
    a node's `config`; this one is a bare dict column on its own table).

    Exactly one of `run_at` (frequency="once") or `time_of_day` (+
    `weekdays` for "weekly", `day_of_month` for "monthly") drives
    `compute_next_run_at` below - see that function's own docstring for the
    per-frequency recurrence rules.
    """

    __tablename__ = "workflow_schedules"

    id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "once" | "daily" | "weekly" | "monthly" - validated at the
    # Pydantic-schema layer (a `Literal`), not a DB `Enum`, matching
    # `Workflow.purpose`'s own "plain string column" simplicity.
    frequency: Mapped[str] = mapped_column(String(20), nullable=False)
    # The exact UTC instant to fire, for frequency="once" only.
    run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # "HH:MM" 24h local time-of-day, for daily/weekly/monthly only.
    time_of_day: Mapped[str | None] = mapped_column(String(5), nullable=True)
    # 0=Monday..6=Sunday, for frequency="weekly" only.
    weekdays: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # 1-31 (clamped to the last day of a shorter month - see
    # `compute_next_run_at`), for frequency="monthly" only.
    day_of_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # IANA tz name (e.g. "UTC", "Asia/Kolkata") - `time_of_day`/`weekdays`/
    # `day_of_month` are all interpreted in this timezone, then converted
    # back to UTC for `next_run_at`.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC", server_default="UTC")
    # `{"kind": "static", "phone_numbers": [...]}` or `{"kind": "module",
    # "module": "...", "filters": {...}, "phone_field": "..."}` - see this
    # class's own docstring.
    recipient_source: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # UTC. Indexed (not just as part of a composite index) since
    # `schedule_poller.poll_once` filters directly on this column across
    # every tenant on every poll pass.
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_status: Mapped[str | None] = mapped_column(String(20), nullable=True)


def _parse_time_of_day(time_of_day: str) -> tuple[int, int]:
    hour_str, minute_str = time_of_day.split(":")
    return int(hour_str), int(minute_str)


def _local_datetime(year: int, month: int, day: int, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=tz)


def _monthly_candidate(year: int, month: int, day_of_month: int, hour: int, minute: int, tz: ZoneInfo) -> datetime:
    """`day_of_month` clamped to the last actual day of `year`/`month` -
    e.g. day_of_month=31 in April (30 days) fires on April 30, never
    skipping the month or raising."""
    last_day = calendar.monthrange(year, month)[1]
    return _local_datetime(year, month, min(day_of_month, last_day), hour, minute, tz)


def _add_month(year: int, month: int) -> tuple[int, int]:
    month += 1
    if month > 12:
        return year + 1, 1
    return year, month


def compute_next_run_at(
    frequency: str,
    time_of_day: str | None,
    weekdays: list[int] | None,
    day_of_month: int | None,
    timezone: str,
    after: datetime,
    *,
    run_at: datetime | None = None,
) -> datetime:
    """The next UTC instant a `WorkflowSchedule` with these recurrence
    fields should fire, strictly after `after` (the last time it fired, or
    now, for the very first computation). Pure and DB-free - unit-testable
    in isolation.

    * "once" — always `run_at` itself (converted to UTC if naive/aware in
      another zone), never recomputed. `run_at` is a keyword-only parameter
      here rather than part of the always-required frequency/time_of_day/
      weekdays/day_of_month/timezone/after shape, since every other
      frequency ignores it entirely; a caller computing a "once" schedule's
      `next_run_at` must pass it explicitly.
    * "daily" — the next occurrence of `time_of_day` (local, in `timezone`)
      strictly after `after`; today if `time_of_day` hasn't passed yet
      today, otherwise tomorrow.
    * "weekly" — the next occurrence of `time_of_day` on any day in
      `weekdays` (0=Monday..6=Sunday) strictly after `after`.
    * "monthly" — the next occurrence of `time_of_day` on `day_of_month`
      (clamped to the last day of a shorter month - see
      `_monthly_candidate`) strictly after `after`.

    Raises `ValueError` for an unknown `frequency`, a missing field a given
    frequency requires, or a naive (no tzinfo) `after`.
    """
    if after.tzinfo is None:
        raise ValueError("after must be timezone-aware")

    if frequency == "once":
        if run_at is None:
            raise ValueError("run_at is required to compute next_run_at for a 'once' schedule")
        return run_at.astimezone(dt_timezone.utc) if run_at.tzinfo else run_at.replace(tzinfo=dt_timezone.utc)

    if not time_of_day:
        raise ValueError(f"time_of_day is required for a {frequency!r} schedule")
    hour, minute = _parse_time_of_day(time_of_day)
    tz = ZoneInfo(timezone)
    after_local = after.astimezone(tz)

    if frequency == "daily":
        candidate = _local_datetime(after_local.year, after_local.month, after_local.day, hour, minute, tz)
        if candidate <= after_local:
            next_day = after_local + timedelta(days=1)
            candidate = _local_datetime(next_day.year, next_day.month, next_day.day, hour, minute, tz)
        return candidate.astimezone(dt_timezone.utc)

    if frequency == "weekly":
        if not weekdays:
            raise ValueError("weekdays is required for a weekly schedule")
        for offset in range(8):
            candidate_day = after_local + timedelta(days=offset)
            if candidate_day.weekday() not in weekdays:
                continue
            candidate = _local_datetime(
                candidate_day.year, candidate_day.month, candidate_day.day, hour, minute, tz
            )
            if candidate > after_local:
                return candidate.astimezone(dt_timezone.utc)
        raise ValueError(f"could not compute next weekly run for weekdays={weekdays!r}")

    if frequency == "monthly":
        if not day_of_month:
            raise ValueError("day_of_month is required for a monthly schedule")
        candidate = _monthly_candidate(after_local.year, after_local.month, day_of_month, hour, minute, tz)
        if candidate <= after_local:
            year, month = _add_month(after_local.year, after_local.month)
            candidate = _monthly_candidate(year, month, day_of_month, hour, minute, tz)
        return candidate.astimezone(dt_timezone.utc)

    raise ValueError(f"unknown schedule frequency: {frequency!r}")
