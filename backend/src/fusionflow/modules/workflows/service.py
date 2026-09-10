"""Workflow domain service — draft/publish lifecycle, simulate, run
queries. None of these commit except where noted; callers (the router)
own the transaction boundary, matching every other module's convention in
this codebase."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.registry import node_executor_registry, trigger_registry
from fusionflow.modules.workflows.engine.run_loop import RunLoopError, execute_run
from fusionflow.modules.workflows.engine.template_resolution import resolve_node_templates
from fusionflow.modules.workflows.models import (
    RunStatus,
    ValidationStatus,
    Workflow,
    WorkflowRun,
    WorkflowStatus,
    WorkflowTrigger,
    WorkflowVersion,
)
from fusionflow.modules.workflows.validation import ValidationResult, validate_for_publish

_EMPTY_GRAPH = {"nodes": [], "edges": []}


class WorkflowServiceError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def create_workflow(
    session: AsyncSession, *, tenant_id: uuid.UUID, name: str, graph: dict, created_by: uuid.UUID
) -> Workflow:
    workflow = Workflow(id=uuid.uuid4(), tenant_id=tenant_id, name=name, status=WorkflowStatus.DRAFT)
    session.add(workflow)
    await session.flush()

    version = WorkflowVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        workflow_id=workflow.id,
        version_number=1,
        graph=graph or dict(_EMPTY_GRAPH),
        created_by=created_by,
    )
    session.add(version)
    await session.flush()
    return workflow


async def list_workflows(session: AsyncSession, *, tenant_id: uuid.UUID) -> list[Workflow]:
    rows = await session.execute(
        select(Workflow).where(Workflow.tenant_id == tenant_id).order_by(Workflow.created_at.desc())
    )
    return list(rows.scalars().all())


async def count_workflows(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Workflow).where(Workflow.tenant_id == tenant_id)
    return (await session.execute(stmt)).scalar_one()


async def get_workflow(session: AsyncSession, workflow_id: uuid.UUID) -> Workflow | None:
    return await session.get(Workflow, workflow_id)


async def get_latest_version(session: AsyncSession, workflow_id: uuid.UUID) -> WorkflowVersion | None:
    rows = await session.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version_number.desc())
        .limit(1)
    )
    return rows.scalars().first()


async def get_draft_version(
    session: AsyncSession, workflow: Workflow, *, created_by: uuid.UUID | None = None
) -> WorkflowVersion:
    """The version PATCH edits.

    If the latest version is already published (immutable — see
    `WorkflowVersion`'s docstring), a new draft version is created cloning
    its graph. If the workflow somehow has zero versions yet (should not
    happen post `create_workflow`, kept defensively), seeds an empty one.
    """
    latest = await get_latest_version(session, workflow.id)
    if latest is None:
        latest = WorkflowVersion(
            id=uuid.uuid4(),
            tenant_id=workflow.tenant_id,
            workflow_id=workflow.id,
            version_number=1,
            graph=dict(_EMPTY_GRAPH),
            created_by=created_by,
        )
        session.add(latest)
        await session.flush()
        return latest

    if latest.published_at is None:
        return latest

    new_version = WorkflowVersion(
        id=uuid.uuid4(),
        tenant_id=workflow.tenant_id,
        workflow_id=workflow.id,
        version_number=latest.version_number + 1,
        graph=dict(latest.graph),
        created_by=created_by,
    )
    session.add(new_version)
    await session.flush()
    return new_version


async def update_workflow(
    session: AsyncSession,
    workflow: Workflow,
    *,
    name: str | None,
    graph: dict | None,
    updated_by: uuid.UUID,
) -> tuple[Workflow, WorkflowVersion]:
    if name is not None:
        workflow.name = name

    version = await get_draft_version(session, workflow, created_by=updated_by)
    if graph is not None:
        version.graph = graph
        # Editing the graph invalidates any prior validation verdict.
        version.validation_status = None
        version.validation_errors = None

    await session.flush()
    return workflow, version


async def publish_workflow(
    session: AsyncSession, workflow: Workflow, *, published_by: uuid.UUID
) -> tuple[Workflow, WorkflowVersion, ValidationResult]:
    version = await get_draft_version(session, workflow, created_by=published_by)
    compiled_graph_json = await resolve_node_templates(session, version.graph)
    graph = WorkflowGraph.from_json(compiled_graph_json)
    result = await validate_for_publish(session, tenant_id=workflow.tenant_id, graph=graph)

    version.validation_status = ValidationStatus.INVALID if result.has_errors else ValidationStatus.VALID
    version.validation_errors = result.to_json()

    if result.has_errors:
        await session.flush()
        return workflow, version, result

    version.compiled_graph = compiled_graph_json
    version.published_at = _now()
    workflow.status = WorkflowStatus.PUBLISHED
    workflow.current_published_version_id = version.id
    await _rebuild_triggers(session, workflow, graph)
    await session.flush()
    return workflow, version, result


async def _rebuild_triggers(session: AsyncSession, workflow: Workflow, graph: WorkflowGraph) -> None:
    """Denormalized `workflow_triggers` index, rebuilt from scratch on
    every successful publish — the outbox poller's O(1) dispatch lookup."""
    existing = (
        await session.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_id == workflow.id))
    ).scalars().all()
    for row in existing:
        await session.delete(row)
    await session.flush()

    trigger_types = {t.trigger_type for t in trigger_registry.all()}
    for node in graph.nodes:
        if node.data.node_type not in trigger_types:
            continue
        session.add(
            WorkflowTrigger(
                id=uuid.uuid4(),
                tenant_id=workflow.tenant_id,
                workflow_id=workflow.id,
                trigger_type=node.data.node_type,
                connector_instance_id=_maybe_uuid(node.data.config.get("connector_instance_id")),
                config=node.data.config,
            )
        )


def _maybe_uuid(value: object) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(str(value))
    except ValueError:
        return None


async def list_versions(session: AsyncSession, workflow_id: uuid.UUID) -> list[WorkflowVersion]:
    rows = await session.execute(
        select(WorkflowVersion)
        .where(WorkflowVersion.workflow_id == workflow_id)
        .order_by(WorkflowVersion.version_number.desc())
    )
    return list(rows.scalars().all())


async def simulate_workflow(session: AsyncSession, workflow: Workflow, *, payload: dict) -> WorkflowRun:
    """Synchronous dry run using the built-in `manual.test_trigger`,
    bypassing the inbox entirely (no outbox row is written). Runs against
    the *latest* version (draft or published) so a workflow can be tested
    before it is ever published."""
    version = await get_latest_version(session, workflow.id)
    if version is None:
        raise WorkflowServiceError(400, "workflow has no draft version yet")

    # Resolved transiently, not persisted - a simulate run always reflects
    # whichever templates are active right now, even pre-publish.
    compiled_graph_json = await resolve_node_templates(session, version.graph)
    graph = WorkflowGraph.from_json(compiled_graph_json)
    run = WorkflowRun(
        id=uuid.uuid4(),
        tenant_id=workflow.tenant_id,
        workflow_id=workflow.id,
        workflow_version_id=version.id,
        trigger_event_ref="simulate",
        status=RunStatus.RUNNING,
        started_at=_now(),
    )
    session.add(run)
    await session.flush()

    try:
        await execute_run(session, run, graph, trigger_payload=payload)
    except RunLoopError as exc:
        run.status = RunStatus.FAILED
        run.completed_at = _now()
        run.trigger_event_ref = f"simulate: {exc}"

    await session.flush()
    return run


async def list_runs(session: AsyncSession, workflow_id: uuid.UUID) -> list[WorkflowRun]:
    rows = await session.execute(
        select(WorkflowRun)
        .where(WorkflowRun.workflow_id == workflow_id)
        .order_by(WorkflowRun.started_at.desc())
    )
    return list(rows.scalars().all())


async def get_run(session: AsyncSession, run_id: uuid.UUID) -> WorkflowRun | None:
    return await session.get(WorkflowRun, run_id)


def list_node_types() -> list:
    """Merged palette metadata from both registries, deduplicated by
    node/trigger type (a built-in trigger like `manual.test_trigger` is
    registered in both `trigger_registry` and `node_executor_registry` —
    see engine/registry.py's module docstring — so this must not list it
    twice)."""
    metas = {t.trigger_type: t.meta() for t in trigger_registry.all()}
    for executor in node_executor_registry.all():
        metas.setdefault(executor.node_type, executor.meta())
    return list(metas.values())


async def list_node_types_with_templates(session: AsyncSession) -> list["schemas.NodeTypeOut"]:
    """`list_node_types()`'s registry-only palette, plus one entry per
    active `WorkflowNodeTemplate` row (modules.admin.models.
    WorkflowNodeTemplate) — the "new integration without a deploy" layer.
    A template whose `base_node_type` isn't currently registered is
    skipped defensively (an admin might add a template before the
    corresponding executor ships in a deploy, or the registry could
    differ between environments)."""
    from fusionflow.modules.admin import service as admin_service
    from fusionflow.modules.workflows import schemas

    entries = [
        schemas.NodeTypeOut(
            node_type=m.node_type,
            kind=m.kind,
            category=m.category,
            subcategory=m.subcategory,
            label=m.label,
            description=m.description,
            config_schema=m.config_schema,
            output_handles=m.output_handles,
            optional_output_handles=m.optional_output_handles,
            can_contain_children=m.can_contain_children,
            child_role=m.child_role,
        )
        for m in list_node_types()
    ]

    templates = await admin_service.list_workflow_node_templates(session, active_only=True)
    for template in templates:
        base_executor = node_executor_registry.get(template.base_node_type)
        if base_executor is None:
            continue
        base_meta = base_executor.meta()
        entries.append(
            schemas.NodeTypeOut(
                node_type=template.key,
                kind=base_meta.kind,
                category=template.category,
                label=template.label,
                description=template.description or base_meta.description,
                config_schema=_merge_config_schema(base_meta.config_schema, template.config_schema_overrides),
                output_handles=base_meta.output_handles,
                optional_output_handles=base_meta.optional_output_handles,
                can_contain_children=base_meta.can_contain_children,
                child_role=base_meta.child_role,
                default_config=template.default_config or {},
                base_node_type=template.base_node_type,
            )
        )
    return entries


def _merge_config_schema(base_schema: dict, overrides: dict | None) -> dict:
    """Shallow-merges `overrides` onto `base_schema`: top-level keys other
    than "properties" replace outright; "properties" merges key-by-key
    (each overridden property replaces its base counterpart entirely,
    rather than a deep per-field merge — enough for the "hide/relabel a
    field, pre-fill its title" use case this exists for, without a full
    JSON-schema merge implementation)."""
    if not overrides:
        return base_schema
    merged = dict(base_schema)
    if "properties" in overrides:
        merged_properties = dict(base_schema.get("properties", {}))
        merged_properties.update(overrides["properties"])
        merged["properties"] = merged_properties
    for key, value in overrides.items():
        if key != "properties":
            merged[key] = value
    return merged
