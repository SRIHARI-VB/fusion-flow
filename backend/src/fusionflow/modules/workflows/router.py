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

from fastapi import APIRouter, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.workflows import schemas, service
from fusionflow.modules.workflows.models import Workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])


async def _get_workflow_or_404(session, tenant_id: uuid.UUID, workflow_id: uuid.UUID) -> Workflow:
    workflow = await service.get_workflow(session, workflow_id)
    if workflow is None or workflow.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


@router.get("/node-types", response_model=list[schemas.NodeTypeOut])
async def get_node_types(context: TenantContextDep) -> list[schemas.NodeTypeOut]:
    """Palette metadata for the workflow builder — pure registry read, no
    DB access needed beyond the tenant-context dependency itself."""
    return [
        schemas.NodeTypeOut(
            node_type=m.node_type,
            kind=m.kind,
            category=m.category,
            label=m.label,
            description=m.description,
            config_schema=m.config_schema,
            output_handles=m.output_handles,
        )
        for m in service.list_node_types()
    ]


@router.get("", response_model=list[schemas.WorkflowOut])
async def list_workflows(context: TenantContextDep, session: SessionDep) -> list[schemas.WorkflowOut]:
    workflows = await service.list_workflows(session, tenant_id=context.tenant_id)
    return [schemas.WorkflowOut.model_validate(w) for w in workflows]


@router.post("", response_model=schemas.WorkflowOut, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    payload: schemas.WorkflowCreateRequest, context: TenantContextDep, session: SessionDep
) -> schemas.WorkflowOut:
    workflow = await service.create_workflow(
        session,
        tenant_id=context.tenant_id,
        name=payload.name,
        graph=payload.graph,
        created_by=context.user.id,
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


@router.get("/runs/{run_id}", response_model=schemas.RunDetailOut)
async def get_run(run_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> schemas.RunDetailOut:
    run = await service.get_run(session, run_id)
    if run is None or run.tenant_id != context.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    await session.refresh(run, attribute_names=["steps"])
    return schemas.RunDetailOut.model_validate(run)
