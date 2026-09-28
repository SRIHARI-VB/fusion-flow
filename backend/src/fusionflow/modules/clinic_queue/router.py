"""`/api/v1/clinic-queue` — the "Patient Flow" Kanban module.

Step-up enforcement: a doctor-flagged member (`Membership.is_doctor`)
must present a valid, unexpired step-up token (`X-Step-Up-Token` header,
minted by `POST /auth/step-up`) on EVERY route in this router - not just
the ones that touch `consultation_notes` - since the frontend's
`RequireStepUp` gate blocks entry to the whole module until that token
exists, so by the time any request reaches here a doctor is expected to
already hold one. A non-doctor member (receptionist/owner/admin) never
needs one: they can never see `consultation_notes` regardless (enforced
structurally in `service.to_patient_visit_out_dict`/`list_history`, not
by this token), so there is nothing extra to protect for them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, status
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.core.security import decode_step_up_token
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.clinic_queue import service as clinic_queue_service
from fusionflow.modules.clinic_queue.models import PatientVisitStage, PaymentMode
from fusionflow.modules.clinic_queue.schemas import (
    DoctorOut,
    PatientCreate,
    VisitStageTransition,
)
from fusionflow.modules.connectors.deps import require_module_access

router = APIRouter(
    prefix="/clinic-queue",
    tags=["clinic-queue"],
    dependencies=[Depends(require_module_access("clinic_queue"))],
)


async def _require_step_up_if_doctor(
    context: TenantContextDep,
    session: SessionDep,
    x_step_up_token: Annotated[str | None, Header()] = None,
) -> TenantContextDep:
    if not await clinic_queue_service.is_doctor_membership(session, tenant_id=context.tenant_id, user_id=context.user.id):
        return context
    if not x_step_up_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Step-up authentication required for doctor access to this module",
        )
    try:
        step_up_user_id = decode_step_up_token(x_step_up_token)
    except Exception as exc:  # noqa: BLE001 - jwt.PyJWTError subclasses + ValueError, both mean "invalid"
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Step-up token invalid or expired"
        ) from exc
    if step_up_user_id != context.user.id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Step-up token does not match the current user")
    return context


StepUpGuardedContext = Annotated[TenantContextDep, Depends(_require_step_up_if_doctor)]


@router.post("/patients", response_model=dict, status_code=status.HTTP_201_CREATED)
async def add_patient(payload: PatientCreate, session: SessionDep, context: StepUpGuardedContext) -> dict:
    visit = await clinic_queue_service.create_patient_visit(session, tenant_id=context.tenant_id, payload=payload)
    await commit_and_keep_tenant_context(session)
    await session.refresh(visit)
    include_notes = await clinic_queue_service.is_doctor_membership(
        session, tenant_id=context.tenant_id, user_id=context.user.id
    )
    out = await clinic_queue_service.to_patient_visit_out_list(
        session, tenant_id=context.tenant_id, visits=[visit], include_notes=include_notes
    )
    return out[0]


@router.get("/visits", response_model=list[dict])
async def list_visits(
    session: SessionDep,
    context: StepUpGuardedContext,
    stage: Annotated[str | None, Query(description="Comma-separated stages, defaults to all non-completed")] = None,
) -> list[dict]:
    stages = None
    if stage:
        try:
            stages = [PatientVisitStage(s.strip()) for s in stage.split(",") if s.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    visits = await clinic_queue_service.list_active_visits(session, tenant_id=context.tenant_id, stages=stages)
    include_notes = await clinic_queue_service.is_doctor_membership(
        session, tenant_id=context.tenant_id, user_id=context.user.id
    )
    return await clinic_queue_service.to_patient_visit_out_list(
        session, tenant_id=context.tenant_id, visits=visits, include_notes=include_notes
    )


@router.patch("/visits/{visit_id}/stage", response_model=dict)
async def update_visit_stage(
    visit_id: uuid.UUID,
    session: SessionDep,
    context: StepUpGuardedContext,
    payload: Annotated[VisitStageTransition, Body(discriminator="stage")],
) -> dict:
    visit = await clinic_queue_service.get_visit(session, tenant_id=context.tenant_id, visit_id=visit_id)
    if visit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Visit not found")
    try:
        visit = await clinic_queue_service.transition_visit_stage(
            session, tenant_id=context.tenant_id, visit=visit, transition=payload
        )
    except clinic_queue_service.StageTransitionError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    await commit_and_keep_tenant_context(session)
    await session.refresh(visit)
    include_notes = await clinic_queue_service.is_doctor_membership(
        session, tenant_id=context.tenant_id, user_id=context.user.id
    )
    out = await clinic_queue_service.to_patient_visit_out_list(
        session, tenant_id=context.tenant_id, visits=[visit], include_notes=include_notes
    )
    return out[0]


@router.get("/history", response_model=list[dict])
async def get_history(
    session: SessionDep,
    context: StepUpGuardedContext,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    doctor_membership_id: uuid.UUID | None = None,
    payment_mode: PaymentMode | None = None,
) -> list[dict]:
    visits = await clinic_queue_service.list_history(
        session,
        tenant_id=context.tenant_id,
        date_from=date_from,
        date_to=date_to,
        doctor_membership_id=doctor_membership_id,
        payment_mode=payment_mode,
    )
    include_notes = await clinic_queue_service.is_doctor_membership(
        session, tenant_id=context.tenant_id, user_id=context.user.id
    )
    return await clinic_queue_service.to_patient_visit_out_list(
        session, tenant_id=context.tenant_id, visits=visits, include_notes=include_notes
    )


@router.get("/doctors", response_model=list[DoctorOut])
async def list_doctors(session: SessionDep, context: StepUpGuardedContext) -> list[DoctorOut]:
    return await clinic_queue_service.list_doctors(session, tenant_id=context.tenant_id)
