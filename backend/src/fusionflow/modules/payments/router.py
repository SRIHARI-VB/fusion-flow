"""`/api/v1/payments` — the `payments` fixed connector (M2).

Write routes are intentionally minimal: payments are normally created by
connector webhooks in a later wave, so only a manual/test `POST /payments`
exists here, no PATCH/DELETE. Not mounted here — see `api.py`'s docstring;
the integration wave mounts `router` from this module under `/api/v1`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.modules.payments import service as payments_service
from fusionflow.modules.payments.schemas import PaymentCreate, PaymentOut

router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("", response_model=list[PaymentOut])
async def list_payments(session: SessionDep, context: TenantContextDep) -> list[PaymentOut]:
    payments = await payments_service.list_payments(session, context.tenant_id)
    return [PaymentOut.model_validate(payment) for payment in payments]


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
async def create_payment(
    payload: PaymentCreate, session: SessionDep, context: TenantContextDep
) -> PaymentOut:
    payment = await payments_service.create_payment(session, context.tenant_id, payload)
    await session.commit()
    await session.refresh(payment)
    return PaymentOut.model_validate(payment)


@router.get("/{payment_id}", response_model=PaymentOut)
async def get_payment(
    payment_id: uuid.UUID, session: SessionDep, context: TenantContextDep
) -> PaymentOut:
    payment = await payments_service.get_payment(session, context.tenant_id, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return PaymentOut.model_validate(payment)
