"""`/workflows` — draft/publish lifecycle, simulate, run history, and the
node-type palette.

NOT mounted here. Whoever owns `fusionflow/api.py` (Wave 0/verification)
adds:

    from fusionflow.modules.workflows.router import router as workflows_router
    api_router.include_router(workflows_router)

matching the pattern already used for `auth_router`/`tenancy_router`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.connectors.deps import enforce_resource_limit, require_module_access
from fusionflow.modules.workflows import module_catalog, schemas, service
from fusionflow.modules.workflows.models import Workflow

router = APIRouter(
    prefix="/workflows",
    tags=["workflows"],
    dependencies=[Depends(require_module_access("workflows"))],
)
_resource_gate = Depends(enforce_resource_limit("workflows", service.count_workflows))


async def _get_workflow_or_404(session, tenant_id: uuid.UUID, workflow_id: uuid.UUID) -> Workflow:
    workflow = await service.get_workflow(session, workflow_id)
    if workflow is None or workflow.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


@router.get("/node-types", response_model=list[schemas.NodeTypeOut])
async def get_node_types(
    context: TenantContextDep,
    session: SessionDep,
    purpose: str | None = Query(
        default=None,
        description=(
            "The calling workflow's purpose ('automation'|'broadcast') - when given, a trigger "
            "node type whose applicable_purposes is set and doesn't include it is excluded. "
            "Omit to see every trigger regardless of purpose."
        ),
    ),
) -> list[schemas.NodeTypeOut]:
    """Palette metadata for the workflow builder: every raw registered
    node type, plus one entry per active admin-managed
    `WorkflowNodeTemplate` row — see `service.list_node_types_with_templates`.
    `purpose` is a plain query param (not derived from a `workflow_id`)
    since this endpoint has never taken one — the frontend already knows
    which purpose the workflow it's editing has (see `schemas.WorkflowOut.purpose`)
    and passes it straight through."""
    return await service.list_node_types_with_templates(session, tenant_id=context.tenant_id, purpose=purpose)


@router.get("/modules", response_model=list[schemas.ModuleCatalogEntryOut])
async def get_modules(context: TenantContextDep, session: SessionDep) -> list[schemas.ModuleCatalogEntryOut]:
    """The unified module picker for `records.query`/`records.upsert`
    (and any future module-sourced node): every fixed module plus this
    tenant's own custom object types, one merged list — see
    `module_catalog.list_modules`."""
    entries = await module_catalog.list_modules(session, tenant_id=context.tenant_id)
    return [
        schemas.ModuleCatalogEntryOut(
            key=e.key,
            label=e.label,
            icon=e.icon,
            category=e.category,
            source=e.source,
            supported_operations=e.supported_operations,
            fields=[schemas.ModuleFieldOut(**f) for f in e.fields],
        )
        for e in entries
    ]


@router.get("/starter-templates", response_model=list[schemas.WorkflowStarterTemplateSummaryOut])
async def get_starter_templates(
    context: TenantContextDep, session: SessionDep
) -> list[schemas.WorkflowStarterTemplateSummaryOut]:
    """Ready-to-use example workflows (composable-builder redesign, Phase 6)
    a tenant can start a new workflow from — see
    `service.create_workflow_from_starter_template`. Tenant-facing (every
    tenant sees the same active templates), unlike `/admin/workflow-starter-templates`
    which manages the underlying catalog."""
    from fusionflow.modules.admin import service as admin_service

    templates = await admin_service.list_workflow_starter_templates(session, active_only=True)
    return [
        schemas.WorkflowStarterTemplateSummaryOut(
            id=t.id,
            key=t.key,
            name=t.name,
            description=t.description,
            category=t.category,
            icon=t.icon,
            required_connector_type_keys=admin_service.compute_required_connector_type_keys(t.graph_json),
            setup_notes=t.setup_notes,
            purpose=admin_service.compute_workflow_purpose(t.graph_json),
        )
        for t in templates
    ]


# --- Workflow components (insertable fragments, composable-builder redesign) -
# Declared before `/{workflow_id}` below (and every other path-param route)
# so a literal "/components" segment is never swallowed as a `workflow_id`
# path parameter - FastAPI matches routes in declaration order, same fix
# already applied for `/starter-templates` above.


@router.get("/components", response_model=list[schemas.WorkflowComponentOut])
async def get_components(context: TenantContextDep, session: SessionDep) -> list[schemas.WorkflowComponentOut]:
    """Every insertable fragment this tenant can use: the admin-curated
    catalog plus this tenant's own saved selections — see
    `service.list_components`."""
    return await service.list_components(session, tenant_id=context.tenant_id)


@router.post("/components", response_model=schemas.WorkflowComponentOut, status_code=status.HTTP_201_CREATED)
async def create_component(
    payload: schemas.WorkflowComponentCreateRequest, context: TenantContextDep, session: SessionDep
) -> schemas.WorkflowComponentOut:
    component = await service.create_user_component(session, tenant_id=context.tenant_id, payload=payload)
    await commit_and_keep_tenant_context(session)
    return schemas.WorkflowComponentOut(
        id=str(component.id),
        name=component.name,
        description=component.description,
        category=component.category,
        icon=component.icon,
        source="user",
        graph_fragment=component.graph_fragment,
        required_object_types=None,
    )


@router.delete("/components/{component_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_component(component_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> None:
    deleted = await service.delete_user_component(session, tenant_id=context.tenant_id, component_id=component_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component not found")
    await commit_and_keep_tenant_context(session)


@router.post("/components/{component_id}/provision", status_code=status.HTTP_204_NO_CONTENT)
async def provision_component(component_id: str, context: TenantContextDep, session: SessionDep) -> None:
    """Auto-provisions any custom object type this component's fragment
    assumes exists — called by the frontend right before merging the
    fragment into the currently-open workflow's canvas."""
    found = await service.provision_component(session, tenant_id=context.tenant_id, component_id=component_id)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Component not found")
    await commit_and_keep_tenant_context(session)


@router.get("", response_model=list[schemas.WorkflowOut])
async def list_workflows(context: TenantContextDep, session: SessionDep) -> list[schemas.WorkflowOut]:
    workflows = await service.list_workflows(session, tenant_id=context.tenant_id)
    return [schemas.WorkflowOut.model_validate(w) for w in workflows]


@router.post("", response_model=schemas.WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: schemas.WorkflowCreateRequest, context: TenantContextDep, session: SessionDep, _gate=_resource_gate
) -> schemas.WorkflowOut:
    if payload.starter_template_id is not None:
        try:
            workflow = await service.create_workflow_from_starter_template(
                session,
                tenant_id=context.tenant_id,
                name=payload.name,
                starter_template_id=payload.starter_template_id,
                created_by=context.user.id,
                purpose=payload.purpose,
            )
        except service.WorkflowServiceError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    else:
        workflow = await service.create_workflow(
            session,
            tenant_id=context.tenant_id,
            name=payload.name,
            graph=payload.graph,
            created_by=context.user.id,
            purpose=payload.purpose,
        )
    await commit_and_keep_tenant_context(session)
    await session.refresh(workflow)
    return schemas.WorkflowOut.model_validate(workflow)


@router.get("/{workflow_id}", response_model=schemas.WorkflowOut)
async def get_workflow(
    workflow_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> schemas.WorkflowOut:
    workflow = await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    return schemas.WorkflowOut.model_validate(workflow)


@router.patch("/{workflow_id}", response_model=schemas.WorkflowVersionOut)
async def update_workflow(
    workflow_id: uuid.UUID,
    payload: schemas.WorkflowUpdateRequest,
    context: TenantContextDep,
    session: SessionDep,
) -> schemas.WorkflowVersionOut:
    workflow = await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    _, version = await service.update_workflow(
        session, workflow, name=payload.name, graph=payload.graph, updated_by=context.user.id
    )
    await commit_and_keep_tenant_context(session)
    await session.refresh(version)
    return schemas.WorkflowVersionOut.model_validate(version)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> None:
    workflow = await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    await service.delete_workflow(session, workflow)
    await commit_and_keep_tenant_context(session)


@router.post("/{workflow_id}/publish", response_model=schemas.PublishResponse)
async def publish_workflow(
    workflow_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> schemas.PublishResponse:
    workflow = await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    workflow, version, result = await service.publish_workflow(
        session, workflow, published_by=context.user.id
    )
    await commit_and_keep_tenant_context(session)
    await session.refresh(workflow)
    await session.refresh(version)
    return schemas.PublishResponse(
        workflow=schemas.WorkflowOut.model_validate(workflow),
        version=schemas.WorkflowVersionOut.model_validate(version),
        valid=not result.has_errors,
        issues=result.to_json(),
    )


@router.get("/{workflow_id}/versions", response_model=list[schemas.WorkflowVersionOut])
async def list_versions(
    workflow_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> list[schemas.WorkflowVersionOut]:
    await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    versions = await service.list_versions(session, workflow_id)
    return [schemas.WorkflowVersionOut.model_validate(v) for v in versions]


@router.post("/{workflow_id}/simulate", response_model=schemas.RunDetailOut)
async def simulate_workflow(
    workflow_id: uuid.UUID,
    payload: schemas.SimulateRequest,
    context: TenantContextDep,
    session: SessionDep,
) -> schemas.RunDetailOut:
    workflow = await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    try:
        run = await service.simulate_workflow(session, workflow, payload=payload.payload)
    except service.WorkflowServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    await commit_and_keep_tenant_context(session)
    await session.refresh(run, attribute_names=["steps"])
    return schemas.RunDetailOut.model_validate(run)


@router.get("/{workflow_id}/runs", response_model=list[schemas.RunOut])
async def list_runs(
    workflow_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> list[schemas.RunOut]:
    await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    runs = await service.list_runs(session, workflow_id)
    return [schemas.RunOut.model_validate(r) for r in runs]


@router.post(
    "/{workflow_id}/schedules", response_model=schemas.WorkflowScheduleOut, status_code=status.HTTP_201_CREATED
)
async def create_schedule(
    workflow_id: uuid.UUID,
    payload: schemas.WorkflowScheduleCreateRequest,
    context: TenantContextDep,
    session: SessionDep,
) -> schemas.WorkflowScheduleOut:
    """Recurring/scheduled bulk-send config (recurring/bulk-messaging
    support) - drives `engine/schedule_poller.py`. Mirrors the run-history
    endpoints' shape (`_get_workflow_or_404` + a plain service call)."""
    workflow = await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    schedule = await service.create_schedule(
        session, tenant_id=context.tenant_id, workflow_id=workflow.id, payload=payload
    )
    await commit_and_keep_tenant_context(session)
    await session.refresh(schedule)
    return schemas.WorkflowScheduleOut.model_validate(schedule)


@router.get("/{workflow_id}/schedules", response_model=list[schemas.WorkflowScheduleOut])
async def list_schedules(
    workflow_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> list[schemas.WorkflowScheduleOut]:
    await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    schedules = await service.list_schedules(session, workflow_id=workflow_id)
    return [schemas.WorkflowScheduleOut.model_validate(s) for s in schedules]


async def _get_schedule_or_404(
    session, tenant_id: uuid.UUID, workflow_id: uuid.UUID, schedule_id: uuid.UUID
):
    schedule = await service.get_schedule(session, schedule_id)
    if schedule is None or schedule.tenant_id != tenant_id or schedule.workflow_id != workflow_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Schedule not found")
    return schedule


@router.patch("/{workflow_id}/schedules/{schedule_id}", response_model=schemas.WorkflowScheduleOut)
async def update_schedule(
    workflow_id: uuid.UUID,
    schedule_id: uuid.UUID,
    payload: schemas.WorkflowScheduleUpdateRequest,
    context: TenantContextDep,
    session: SessionDep,
) -> schemas.WorkflowScheduleOut:
    """Also how a schedule is paused/resumed - `{"is_active": false}`/
    `{"is_active": true}` - see `service.update_schedule`'s docstring."""
    await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    schedule = await _get_schedule_or_404(session, context.tenant_id, workflow_id, schedule_id)
    schedule = await service.update_schedule(session, schedule, payload=payload)
    await commit_and_keep_tenant_context(session)
    await session.refresh(schedule)
    return schemas.WorkflowScheduleOut.model_validate(schedule)


@router.delete("/{workflow_id}/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    workflow_id: uuid.UUID, schedule_id: uuid.UUID, context: TenantContextDep, session: SessionDep
) -> None:
    await _get_workflow_or_404(session, context.tenant_id, workflow_id)
    schedule = await _get_schedule_or_404(session, context.tenant_id, workflow_id, schedule_id)
    await service.delete_schedule(session, schedule)
    await commit_and_keep_tenant_context(session)


@router.get("/runs/{run_id}", response_model=schemas.RunDetailOut)
async def get_run(run_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> schemas.RunDetailOut:
    run = await service.get_run(session, run_id)
    if run is None or run.tenant_id != context.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    await session.refresh(run, attribute_names=["steps"])
    return schemas.RunDetailOut.model_validate(run)
