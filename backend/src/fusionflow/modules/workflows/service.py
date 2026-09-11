"""Workflow domain service — draft/publish lifecycle, simulate, run
queries. None of these commit except where noted; callers (the router)
own the transaction boundary, matching every other module's convention in
this codebase."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.models import ConnectorCategory, ConnectorState, ConnectorType
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.registry import node_executor_registry, trigger_registry
from fusionflow.modules.workflows.engine.run_loop import RunLoopError, execute_run
from fusionflow.modules.workflows.engine.template_resolution import (
    resolve_composite_branches,
    resolve_node_templates,
)
from fusionflow.modules.workflows.models import (
    RunStatus,
    ValidationStatus,
    Workflow,
    WorkflowRun,
    WorkflowStatus,
    WorkflowTrigger,
    WorkflowUserComponent,
    WorkflowVersion,
)
from fusionflow.modules.workflows.validation import ValidationResult, validate_for_publish

_EMPTY_GRAPH = {"nodes": [], "edges": []}

logger = logging.getLogger(__name__)


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


async def provision_required_object_types(
    session: AsyncSession, *, tenant_id: uuid.UUID, specs: list[dict[str, Any]] | None
) -> None:
    """Auto-provisions any custom business object type a starter template's
    or component's graph assumes exists (composable-builder redesign) -
    shared by `create_workflow_from_starter_template` and
    `list`/insertion of a `WorkflowComponent`/`WorkflowUserComponent`
    (extracted from what was originally `create_workflow_from_starter_template`'s
    own inline loop, so both callers get the exact same idempotency rule
    from one place).

    For each spec: if this tenant already has an active object type under
    that `key`, it is left completely untouched (a deliberately simple
    idempotency rule - this never overwrites/merges a tenant's own
    customization of an object type they already have, it only fills the
    gap when one doesn't exist yet). Otherwise, creates it (plus one field
    definition per entry in `spec["fields"]`) so a `records.query`/
    `records.upsert` node referencing that module key resolves
    immediately, with zero manual setup.
    """
    # Local import: avoids a module-load-order dependency between
    # `workflows` and `business_objects` for every other caller of this
    # file, which doesn't need it.
    from fusionflow.modules.business_objects import service as business_objects_service
    from fusionflow.modules.business_objects.schemas import ObjectFieldDefinitionCreate, ObjectTypeCreate

    for spec in specs or []:
        existing = await business_objects_service.get_object_type_by_key(
            session, tenant_id=tenant_id, key=spec["key"]
        )
        if existing is not None:
            continue
        object_type = await business_objects_service.create_object_type(
            session,
            tenant_id=tenant_id,
            payload=ObjectTypeCreate(key=spec["key"], name=spec["name"], icon=spec.get("icon")),
        )
        for field_spec in spec.get("fields", []):
            await business_objects_service.create_field_definition(
                session,
                tenant_id=tenant_id,
                object_type_id=object_type.id,
                payload=ObjectFieldDefinitionCreate(
                    key=field_spec["key"],
                    label=field_spec["label"],
                    field_type=field_spec["field_type"],
                    options=field_spec.get("options"),
                    required=field_spec.get("required", False),
                    sort_order=field_spec.get("sort_order", 0),
                ),
            )


async def create_workflow_from_starter_template(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str,
    starter_template_id: uuid.UUID,
    created_by: uuid.UUID,
) -> Workflow:
    """Seeds a new workflow's graph from a `WorkflowStarterTemplate`
    (composable-builder redesign, Phase 6), auto-provisioning any custom
    business object type the template's graph assumes exists (see
    `provision_required_object_types`)."""
    # Local import: avoids a module-load-order dependency between
    # `workflows` and `admin` for every other caller of this file, which
    # doesn't need it.
    from fusionflow.modules.admin import service as admin_service

    template = await admin_service.get_workflow_starter_template(session, starter_template_id)
    if template is None or not template.is_active:
        raise WorkflowServiceError(404, "Starter template not found")

    await provision_required_object_types(session, tenant_id=tenant_id, specs=template.required_object_types)

    return await create_workflow(
        session, tenant_id=tenant_id, name=name, graph=template.graph_json, created_by=created_by
    )


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


async def delete_workflow(session: AsyncSession, workflow: Workflow) -> None:
    """Deletes `workflow` and everything hanging off it - `WorkflowVersion`,
    `WorkflowRun`/`WorkflowRunStep`, and `WorkflowTrigger` rows all have
    `ForeignKey("workflows.id", ondelete="CASCADE")` (or cascade transitively
    from `workflow_runs.id`), so a plain delete of the parent row is
    sufficient; no manual child cleanup needed. Doesn't commit - the caller
    (the router) owns the transaction boundary, matching every other
    function in this file."""
    await session.delete(workflow)


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
    compiled_graph_json = resolve_composite_branches(compiled_graph_json)
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
    compiled_graph_json = resolve_composite_branches(compiled_graph_json)
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


_PALETTE_GROUP_BY_CATEGORY = {
    "Messages": "Talk to Customer",
    "Messaging": "Talk to Customer",
    "Choices": "Talk to Customer",
    "Conditions": "Flow Control",
    "Flow Control": "Flow Control",
    "Ecommerce": "Records",
    "Support": "Records",
    "Customers": "Records",
    "Data": "Advanced",
    "Integrations": "Advanced",
    "Actions": "Advanced",
}


def _default_palette_group(kind: str, category: str) -> str:
    """Best-effort task-oriented bucket for a node type that doesn't
    declare `palette_group` explicitly — every pre-redesign node type,
    plus any future one an author forgets to set. Triggers always bucket
    under "Triggers" regardless of their `category` string; everything
    else falls back through `_PALETTE_GROUP_BY_CATEGORY`, defaulting to
    "Advanced" (the safe, collapsed-by-default catch-all) for an unknown
    category rather than guessing a friendlier bucket it hasn't earned."""
    if kind == "trigger":
        return "Triggers"
    return _PALETTE_GROUP_BY_CATEGORY.get(category, "Advanced")


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


async def list_node_types_with_templates(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list["schemas.NodeTypeOut"]:
    """`list_node_types()`'s registry-only palette, plus one entry per
    active `WorkflowNodeTemplate` row (modules.admin.models.
    WorkflowNodeTemplate) — the "new integration without a deploy" layer —
    filtered down to what this tenant is actually entitled to see (Phase 7
    Part A), and annotated with tenant-specific `field_suggestions` (Part C).

    A template whose `base_node_type` isn't currently registered is
    skipped defensively (an admin might add a template before the
    corresponding executor ships in a deploy, or the registry could
    differ between environments). A template with no `required_connector_type_key`
    of its own inherits its base executor's requirement rather than
    bypassing entitlement filtering entirely - an admin has to explicitly
    set the column to narrow/relax it.
    """
    from fusionflow.modules.admin import service as admin_service
    from fusionflow.modules.workflows import schemas

    # Built as plain dicts first, not `NodeTypeOut` - filtering still has
    # to run before the final response models (which also need
    # `field_suggestions`, not knowable yet at this point) are worth
    # constructing.
    raw_entries: list[dict[str, Any]] = [
        {
            "node_type": m.node_type,
            "kind": m.kind,
            "category": m.category,
            "subcategory": m.subcategory,
            "label": m.label,
            "description": m.description,
            "config_schema": m.config_schema,
            "output_handles": m.output_handles,
            "optional_output_handles": m.optional_output_handles,
            "can_contain_children": m.can_contain_children,
            "child_role": m.child_role,
            "output_schema": m.output_schema,
            "required_connector_type_key": m.required_connector_type_key,
            "default_config": {},
            "base_node_type": None,
            "icon": m.icon,
            "palette_group": m.palette_group or _default_palette_group(m.kind, m.category),
        }
        for m in list_node_types()
    ]

    templates = await admin_service.list_workflow_node_templates(session, active_only=True)
    for template in templates:
        base_executor = node_executor_registry.get(template.base_node_type)
        if base_executor is None:
            continue
        base_meta = base_executor.meta()
        raw_entries.append(
            {
                "node_type": template.key,
                "kind": base_meta.kind,
                "category": template.category,
                "subcategory": None,
                "label": template.label,
                "description": template.description or base_meta.description,
                "config_schema": _merge_config_schema(base_meta.config_schema, template.config_schema_overrides),
                "output_handles": base_meta.output_handles,
                "optional_output_handles": base_meta.optional_output_handles,
                "can_contain_children": base_meta.can_contain_children,
                "child_role": base_meta.child_role,
                "output_schema": base_meta.output_schema,
                "required_connector_type_key": (
                    template.required_connector_type_key or base_meta.required_connector_type_key
                ),
                "default_config": template.default_config or {},
                "base_node_type": template.base_node_type,
                "icon": template.icon or base_meta.icon,
                # Template-backed entries wrap a generic executor
                # (`connector.action`, `module.*`, `http.request`, ...) -
                # they default to "Advanced" rather than inheriting the
                # base executor's own bucket, since the friendly-labeled
                # template is still a raw-config wrapper, not one of the
                # new composable building blocks. A future composite-node
                # template could still override this via its base
                # executor's own `palette_group`.
                "palette_group": base_meta.palette_group or "Advanced",
            }
        )

    # --- Entitlement filtering (Part A) + suggestion sources (Part C),
    # sharing one `get_connector_access_map` call as required by the plan.
    required_keys = {
        e["required_connector_type_key"] for e in raw_entries if e["required_connector_type_key"]
    }

    all_connector_types = await connector_service.list_connector_types(session)
    feature_types = [t for t in all_connector_types if t.category == ConnectorCategory.FEATURE]
    feature_keys = {t.key for t in feature_types}

    key_to_type: dict[str, ConnectorType] = {t.key: t for t in feature_types}
    for key in required_keys | feature_keys:
        if key in key_to_type:
            continue
        connector_type = await connector_service.get_connector_type_by_key(session, key)
        if connector_type is None:
            logger.warning("workflow node palette: unknown connector_type_key %r referenced", key)
            continue
        key_to_type[key] = connector_type

    access_map = await connector_service.get_connector_access_map(
        session, tenant_id=tenant_id, connector_type_ids=[t.id for t in key_to_type.values()]
    )

    def _is_granted(key: str) -> bool:
        connector_type = key_to_type.get(key)
        return connector_type is not None and access_map.get(connector_type.id) == "granted"

    surviving = [
        e
        for e in raw_entries
        if e["required_connector_type_key"] is None or _is_granted(e["required_connector_type_key"])
    ]

    instances = await connector_service.list_instances(session, tenant_id)
    connected_instances = [i for i in instances if i.state == ConnectorState.CONNECTED]
    granted_feature_types = [t for t in feature_types if _is_granted(t.key)]

    entries: list["schemas.NodeTypeOut"] = []
    for e in surviving:
        properties = (e["config_schema"] or {}).get("properties", {})
        field_suggestions: dict[str, list[dict[str, str]]] | None = None

        if "connector_instance_id" in properties:
            required_key = e["required_connector_type_key"]
            if required_key is not None:
                target_type = key_to_type.get(required_key)
                options = [
                    {"value": str(instance.id), "label": instance.display_name}
                    for instance in connected_instances
                    if target_type is not None and instance.connector_type_id == target_type.id
                ]
            else:
                # `connector.action` (and any template built over it with no
                # explicit gate): every connected instance across every
                # currently-granted type, label prefixed by connector type.
                options = [
                    {
                        "value": str(instance.id),
                        "label": f"{instance.connector_type.display_name} — {instance.display_name}",
                    }
                    for instance in connected_instances
                    if _is_granted(instance.connector_type.key)
                ]
            field_suggestions = {"connector_instance_id": options}
        elif "module" in properties:
            field_suggestions = {
                "module": [{"value": t.key, "label": t.display_name} for t in granted_feature_types]
            }

        entries.append(
            schemas.NodeTypeOut(
                node_type=e["node_type"],
                kind=e["kind"],
                category=e["category"],
                subcategory=e["subcategory"],
                label=e["label"],
                description=e["description"],
                config_schema=e["config_schema"],
                output_handles=e["output_handles"],
                optional_output_handles=e["optional_output_handles"],
                can_contain_children=e["can_contain_children"],
                child_role=e["child_role"],
                default_config=e["default_config"],
                base_node_type=e["base_node_type"],
                required_connector_type_key=e["required_connector_type_key"],
                output_schema=e["output_schema"],
                field_suggestions=field_suggestions,
                icon=e["icon"],
                palette_group=e["palette_group"],
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


# --- Workflow components (insertable fragments, composable-builder redesign) -


async def list_components(session: AsyncSession, *, tenant_id: uuid.UUID) -> list["schemas.WorkflowComponentOut"]:
    """Merges the admin-curated `WorkflowComponent` catalog and this
    tenant's own saved `WorkflowUserComponent` rows into one list - the
    `records.query`/`whatsapp.ask_choice` "one merged module picker"
    pattern, applied here to component sources instead of modules."""
    from fusionflow.modules.admin import service as admin_service
    from fusionflow.modules.workflows import schemas

    entries: list[schemas.WorkflowComponentOut] = []

    admin_components = await admin_service.list_workflow_components(session, active_only=True)
    for component in admin_components:
        entries.append(
            schemas.WorkflowComponentOut(
                id=str(component.id),
                name=component.name,
                description=component.description,
                category=component.category,
                icon=component.icon,
                source="admin",
                graph_fragment=component.graph_fragment,
                required_object_types=component.required_object_types,
            )
        )

    rows = await session.execute(
        select(WorkflowUserComponent)
        .where(WorkflowUserComponent.tenant_id == tenant_id)
        .order_by(WorkflowUserComponent.created_at.desc())
    )
    for component in rows.scalars().all():
        entries.append(
            schemas.WorkflowComponentOut(
                id=str(component.id),
                name=component.name,
                description=component.description,
                category=component.category,
                icon=component.icon,
                source="user",
                graph_fragment=component.graph_fragment,
                required_object_types=None,
            )
        )

    return entries


async def _resolve_component(
    session: AsyncSession, *, tenant_id: uuid.UUID, component_id: str
) -> tuple[dict[str, Any], list[dict[str, Any]] | None] | None:
    """Resolves `component_id` (a plain UUID string either way - see
    `schemas.WorkflowComponentOut.id`'s docstring) against the admin
    catalog first, then this tenant's own saved components. Returns
    `(graph_fragment, required_object_types)` or `None` if neither table
    has a matching (and, for the user table, tenant-owned) row."""
    from fusionflow.modules.admin import service as admin_service

    try:
        parsed_id = uuid.UUID(component_id)
    except ValueError:
        return None

    admin_component = await admin_service.get_workflow_component(session, parsed_id)
    if admin_component is not None and admin_component.is_active:
        return admin_component.graph_fragment, admin_component.required_object_types

    user_component = await session.get(WorkflowUserComponent, parsed_id)
    if user_component is not None and user_component.tenant_id == tenant_id:
        return user_component.graph_fragment, None

    return None


async def provision_component(session: AsyncSession, *, tenant_id: uuid.UUID, component_id: str) -> bool:
    """Auto-provisions whatever custom object type(s) the named component's
    fragment assumes exist (see `provision_required_object_types`) - called
    right before the frontend merges the fragment into the canvas. Returns
    `False` if `component_id` doesn't resolve to a component this tenant
    can see (caller returns 404)."""
    resolved = await _resolve_component(session, tenant_id=tenant_id, component_id=component_id)
    if resolved is None:
        return False
    _graph_fragment, required_object_types = resolved
    await provision_required_object_types(session, tenant_id=tenant_id, specs=required_object_types)
    return True


async def create_user_component(
    session: AsyncSession, *, tenant_id: uuid.UUID, payload: "schemas.WorkflowComponentCreateRequest"
) -> WorkflowUserComponent:
    component = WorkflowUserComponent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=payload.name,
        description=payload.description,
        category=payload.category or "Custom",
        icon=payload.icon,
        graph_fragment=payload.graph_fragment,
    )
    session.add(component)
    await session.flush()
    return component


async def delete_user_component(session: AsyncSession, *, tenant_id: uuid.UUID, component_id: uuid.UUID) -> bool:
    """Only ever deletes a row from `workflow_user_components` scoped to
    this tenant - there is no path from this function to the admin-curated
    `WorkflowComponent` table at all, by construction (different model,
    different session query), not just by a tenant_id check."""
    component = await session.get(WorkflowUserComponent, component_id)
    if component is None or component.tenant_id != tenant_id:
        return False
    await session.delete(component)
    await session.flush()
    return True
