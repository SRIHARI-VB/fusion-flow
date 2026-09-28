from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.clinic_queue.models import PatientVisitStage, PaymentMode


class PatientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=40)
    assigned_doctor_membership_id: uuid.UUID | None = None
    appointment_ref_id: uuid.UUID | None = None


class VisitStageAssignDoctor(BaseModel):
    stage: Literal[PatientVisitStage.WITH_DOCTOR] = PatientVisitStage.WITH_DOCTOR
    assigned_doctor_membership_id: uuid.UUID


class VisitStageToBilling(BaseModel):
    stage: Literal[PatientVisitStage.BILLING] = PatientVisitStage.BILLING
    consultation_notes: str = Field(min_length=1)
    amount_to_collect: Decimal = Field(ge=0)


class VisitStageComplete(BaseModel):
    stage: Literal[PatientVisitStage.COMPLETED] = PatientVisitStage.COMPLETED
    payment_mode: PaymentMode
    amount_collected: Decimal | None = Field(default=None, ge=0)


# A `discriminator` union on `stage` gives a precise 422 naming exactly
# which fields are missing for the target stage the caller asked for,
# rather than a generic "invalid body" - this is what makes "one PATCH
# call per drag-drop action" actually safe for the frontend to rely on.
VisitStageTransition = VisitStageAssignDoctor | VisitStageToBilling | VisitStageComplete


class DoctorOut(BaseModel):
    membership_id: uuid.UUID
    name: str
    email: str


class PatientVisitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    customer_phone: str | None
    appointment_ref_id: uuid.UUID | None
    assigned_doctor_membership_id: uuid.UUID | None
    assigned_doctor_name: str | None
    stage: PatientVisitStage
    checked_in_at: datetime
    doctor_started_at: datetime | None
    # Omitted entirely (not null) for a non-doctor requester - see
    # `service.to_patient_visit_out`'s `include_notes` parameter. Pydantic
    # only excludes a field from JSON when it's both optional AND actually
    # left unset at construction time (not just set to None), which is
    # exactly the "absent, not blank" contract the doctor-only visibility
    # requirement needs - verified in this module's own smoke test.
    consultation_notes: str | None = Field(default=None)
    amount_to_collect: Decimal | None
    billing_started_at: datetime | None
    payment_mode: PaymentMode | None
    amount_collected: Decimal | None
    completed_at: datetime | None
    position: int
    created_at: datetime
    updated_at: datetime
