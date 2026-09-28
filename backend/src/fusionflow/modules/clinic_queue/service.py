"""Service layer for the "Patient Flow" clinic-queue Kanban module.

`Membership.user` has no display-name column (only `email` - see
`modules/auth/models.py`), matching the same constraint `Sidebar.tsx`'s
`initials = email.split("@")[0]...` already works around on the frontend.
`_display_name` here applies the identical fallback so a doctor's
"name" is at least the human-friendly part of their email, not a raw
address - there is no better source of truth to pull from today.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.auth.models import User
from fusionflow.modules.business_objects import service as business_objects_service
from fusionflow.modules.business_objects.schemas import ObjectFieldDefinitionUpdate
from fusionflow.modules.clinic_queue.models import PatientVisit, PatientVisitStage, PaymentMode
from fusionflow.modules.clinic_queue.schemas import (
    DoctorOut,
    PatientCreate,
    VisitStageAssignDoctor,
    VisitStageComplete,
    VisitStageToBilling,
    VisitStageTransition,
)
from fusionflow.modules.customers import service as customers_service
from fusionflow.modules.customers.models import Customer
from fusionflow.modules.customers.schemas import CustomerCreate
from fusionflow.modules.tenancy.models import Membership

_ACTIVE_STAGES = (PatientVisitStage.RECEPTION, PatientVisitStage.WITH_DOCTOR, PatientVisitStage.BILLING)


def _display_name(email: str) -> str:
    return email.split("@")[0]


async def find_or_create_patient_customer(
    session: AsyncSession, *, tenant_id: uuid.UUID, name: str, phone: str
) -> Customer:
    """Reuses the existing phone-based customer lookup (the same bridge
    `whatsapp.find_or_create_customer` already uses) rather than
    duplicating it - a patient who has also messaged a connected channel
    is the same underlying `Customer` row, not a separate identity."""
    existing = await customers_service.get_customer_by_phone(session, tenant_id, phone)
    if existing is not None:
        return existing
    return await customers_service.create_customer(
        session, tenant_id, CustomerCreate(name=name, phone=phone)
    )


async def _next_position(session: AsyncSession, tenant_id: uuid.UUID, stage: PatientVisitStage) -> int:
    max_position = (
        await session.execute(
            select(func.max(PatientVisit.position)).where(
                PatientVisit.tenant_id == tenant_id, PatientVisit.stage == stage
            )
        )
    ).scalar_one()
    return (max_position or 0) + 1


async def create_patient_visit(
    session: AsyncSession, *, tenant_id: uuid.UUID, payload: PatientCreate
) -> PatientVisit:
    customer = await find_or_create_patient_customer(
        session, tenant_id=tenant_id, name=payload.name, phone=payload.phone
    )
    visit = PatientVisit(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        customer_id=customer.id,
        appointment_ref_id=payload.appointment_ref_id,
        assigned_doctor_membership_id=payload.assigned_doctor_membership_id,
        stage=PatientVisitStage.RECEPTION,
        checked_in_at=datetime.now(timezone.utc),
        position=await _next_position(session, tenant_id, PatientVisitStage.RECEPTION),
    )
    session.add(visit)
    await session.flush()
    return visit


async def get_visit(session: AsyncSession, *, tenant_id: uuid.UUID, visit_id: uuid.UUID) -> PatientVisit | None:
    return (
        await session.execute(
            select(PatientVisit).where(PatientVisit.id == visit_id, PatientVisit.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def list_active_visits(
    session: AsyncSession, *, tenant_id: uuid.UUID, stages: list[PatientVisitStage] | None = None
) -> list[PatientVisit]:
    target_stages = stages or list(_ACTIVE_STAGES)
    rows = await session.execute(
        select(PatientVisit)
        .where(PatientVisit.tenant_id == tenant_id, PatientVisit.stage.in_(target_stages))
        .order_by(PatientVisit.stage, PatientVisit.position)
    )
    return list(rows.scalars().all())


class StageTransitionError(ValueError):
    """Raised for a structurally-valid-but-semantically-wrong transition
    (e.g. completing a visit that's still in reception) - the router
    turns this into a 409, distinct from a 422 body-validation failure."""


_APPOINTMENT_COMPLETED_STATUS = "completed"


async def _sync_appointment_status_on_completion(session: AsyncSession, *, tenant_id: uuid.UUID, appointment_ref_id: uuid.UUID) -> None:
    """Best-effort: a visit can complete even if its originating
    appointment record was since deleted or the field can't be updated -
    the billing transaction itself must not fail because of this."""
    record = await business_objects_service.get_record(session, tenant_id=tenant_id, record_id=appointment_ref_id)
    if record is None:
        return
    object_type = await business_objects_service.get_object_type(session, tenant_id=tenant_id, object_type_id=record.object_type_id)
    if object_type is None:
        return
    field_defs = await business_objects_service.list_field_definitions(
        session, tenant_id=tenant_id, object_type_id=object_type.id
    )
    status_field = next((f for f in field_defs if f.key == "status"), None)
    if status_field is not None and _APPOINTMENT_COMPLETED_STATUS not in (status_field.options or []):
        await business_objects_service.update_field_definition(
            session,
            status_field,
            ObjectFieldDefinitionUpdate(options=[*(status_field.options or []), _APPOINTMENT_COMPLETED_STATUS]),
        )
    await business_objects_service.update_record(
        session, record, field_defs=field_defs, payload={"status": _APPOINTMENT_COMPLETED_STATUS}
    )


async def transition_visit_stage(
    session: AsyncSession, *, tenant_id: uuid.UUID, visit: PatientVisit, transition: VisitStageTransition
) -> PatientVisit:
    now = datetime.now(timezone.utc)

    if isinstance(transition, VisitStageAssignDoctor):
        if visit.stage != PatientVisitStage.RECEPTION:
            raise StageTransitionError("Only a visit in reception can be assigned to a doctor")
        visit.assigned_doctor_membership_id = transition.assigned_doctor_membership_id
        visit.stage = PatientVisitStage.WITH_DOCTOR
        visit.doctor_started_at = now
    elif isinstance(transition, VisitStageToBilling):
        if visit.stage != PatientVisitStage.WITH_DOCTOR:
            raise StageTransitionError("Only a visit with a doctor can move to billing")
        visit.consultation_notes = transition.consultation_notes
        visit.amount_to_collect = transition.amount_to_collect
        visit.stage = PatientVisitStage.BILLING
        visit.billing_started_at = now
    elif isinstance(transition, VisitStageComplete):
        if visit.stage != PatientVisitStage.BILLING:
            raise StageTransitionError("Only a visit in billing can be completed")
        visit.payment_mode = transition.payment_mode
        visit.amount_collected = (
            transition.amount_collected if transition.amount_collected is not None else visit.amount_to_collect
        )
        visit.stage = PatientVisitStage.COMPLETED
        visit.completed_at = now
        if visit.appointment_ref_id is not None:
            await _sync_appointment_status_on_completion(
                session, tenant_id=tenant_id, appointment_ref_id=visit.appointment_ref_id
            )
    else:  # pragma: no cover - exhaustive per the discriminated union
        raise StageTransitionError(f"Unhandled transition {transition!r}")

    visit.position = await _next_position(session, tenant_id, visit.stage)
    await session.flush()
    return visit


async def is_doctor_membership(session: AsyncSession, *, tenant_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    membership = (
        await session.execute(
            select(Membership).where(Membership.business_id == tenant_id, Membership.user_id == user_id)
        )
    ).scalar_one_or_none()
    return bool(membership and membership.is_doctor)


async def list_doctors(session: AsyncSession, *, tenant_id: uuid.UUID) -> list[DoctorOut]:
    rows = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.business_id == tenant_id, Membership.is_doctor.is_(True))
    )
    return [
        DoctorOut(membership_id=membership.id, name=_display_name(user.email), email=user.email)
        for membership, user in rows.all()
    ]


async def _load_names(
    session: AsyncSession, *, tenant_id: uuid.UUID, visits: list[PatientVisit]
) -> tuple[dict[uuid.UUID, Customer], dict[uuid.UUID, str]]:
    customer_ids = {v.customer_id for v in visits}
    doctor_membership_ids = {v.assigned_doctor_membership_id for v in visits if v.assigned_doctor_membership_id}

    customers_by_id: dict[uuid.UUID, Customer] = {}
    if customer_ids:
        rows = await session.execute(select(Customer).where(Customer.id.in_(customer_ids)))
        customers_by_id = {c.id: c for c in rows.scalars().all()}

    doctor_names: dict[uuid.UUID, str] = {}
    if doctor_membership_ids:
        rows = await session.execute(
            select(Membership.id, User.email)
            .join(User, User.id == Membership.user_id)
            .where(Membership.id.in_(doctor_membership_ids))
        )
        doctor_names = {membership_id: _display_name(email) for membership_id, email in rows.all()}

    return customers_by_id, doctor_names


def to_patient_visit_out_dict(
    visit: PatientVisit, *, customer: Customer, doctor_name: str | None, include_notes: bool
) -> dict[str, Any]:
    """Returns a plain dict, not a constructed `PatientVisitOut`, so
    `consultation_notes` can be a TRULY absent key (not `null`) for a
    non-doctor requester - verified via `model_dump(exclude_unset=True)`
    against `.model_construct()` before relying on this in the router;
    a plain dict sidesteps needing every caller to remember that flag."""
    out: dict[str, Any] = {
        "id": visit.id,
        "customer_id": visit.customer_id,
        "customer_name": customer.name,
        "customer_phone": customer.phone,
        "appointment_ref_id": visit.appointment_ref_id,
        "assigned_doctor_membership_id": visit.assigned_doctor_membership_id,
        "assigned_doctor_name": doctor_name,
        "stage": visit.stage,
        "checked_in_at": visit.checked_in_at,
        "doctor_started_at": visit.doctor_started_at,
        "amount_to_collect": visit.amount_to_collect,
        "billing_started_at": visit.billing_started_at,
        "payment_mode": visit.payment_mode,
        "amount_collected": visit.amount_collected,
        "completed_at": visit.completed_at,
        "position": visit.position,
        "created_at": visit.created_at,
        "updated_at": visit.updated_at,
    }
    if include_notes:
        out["consultation_notes"] = visit.consultation_notes
    return out


async def to_patient_visit_out_list(
    session: AsyncSession, *, tenant_id: uuid.UUID, visits: list[PatientVisit], include_notes: bool
) -> list[dict[str, Any]]:
    customers_by_id, doctor_names = await _load_names(session, tenant_id=tenant_id, visits=visits)
    return [
        to_patient_visit_out_dict(
            v,
            customer=customers_by_id[v.customer_id],
            doctor_name=doctor_names.get(v.assigned_doctor_membership_id) if v.assigned_doctor_membership_id else None,
            include_notes=include_notes,
        )
        for v in visits
    ]


async def list_history(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    date_from: datetime | None,
    date_to: datetime | None,
    doctor_membership_id: uuid.UUID | None,
    payment_mode: PaymentMode | None,
) -> list[PatientVisit]:
    query = select(PatientVisit).where(
        PatientVisit.tenant_id == tenant_id, PatientVisit.stage == PatientVisitStage.COMPLETED
    )
    if date_from is not None:
        query = query.where(PatientVisit.completed_at >= date_from)
    if date_to is not None:
        query = query.where(PatientVisit.completed_at <= date_to)
    if doctor_membership_id is not None:
        query = query.where(PatientVisit.assigned_doctor_membership_id == doctor_membership_id)
    if payment_mode is not None:
        query = query.where(PatientVisit.payment_mode == payment_mode)
    query = query.order_by(PatientVisit.completed_at.desc())
    rows = await session.execute(query)
    return list(rows.scalars().all())
