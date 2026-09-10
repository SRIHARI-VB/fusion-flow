"""`/api/v1/customers` — the `customers` fixed connector (M2).

Not mounted here — see `api.py`'s docstring; the integration wave mounts
`router` from this module under the `/api/v1` group.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.connectors.deps import enforce_resource_limit, require_module_access
from fusionflow.modules.customers import service as customers_service
from fusionflow.modules.customers.schemas import CustomerCreate, CustomerOut, CustomerUpdate

router = APIRouter(
    prefix="/customers",
    tags=["customers"],
    dependencies=[Depends(require_module_access("customers"))],
)
_resource_gate = Depends(enforce_resource_limit("customers", customers_service.count_customers))


@router.get("", response_model=list[CustomerOut])
async def list_customers(session: SessionDep, context: TenantContextDep) -> list[CustomerOut]:
    customers = await customers_service.list_customers(session, context.tenant_id)
    return [CustomerOut.model_validate(customer) for customer in customers]


@router.post("", response_model=CustomerOut, status_code=status.HTTP_201_CREATED)
async def create_customer(
    payload: CustomerCreate, session: SessionDep, context: TenantContextDep, _gate=_resource_gate
) -> CustomerOut:
    customer = await customers_service.create_customer(session, context.tenant_id, payload)
    await commit_and_keep_tenant_context(session)
    await session.refresh(customer)
    return CustomerOut.model_validate(customer)


@router.get("/{customer_id}", response_model=CustomerOut)
async def get_customer(
    customer_id: uuid.UUID, session: SessionDep, context: TenantContextDep
) -> CustomerOut:
    customer = await customers_service.get_customer(session, context.tenant_id, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return CustomerOut.model_validate(customer)


@router.patch("/{customer_id}", response_model=CustomerOut)
async def update_customer(
    customer_id: uuid.UUID,
    payload: CustomerUpdate,
    session: SessionDep,
    context: TenantContextDep,
) -> CustomerOut:
    customer = await customers_service.get_customer(session, context.tenant_id, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    customer = await customers_service.update_customer(session, customer, payload)
    await commit_and_keep_tenant_context(session)
    await session.refresh(customer)
    return CustomerOut.model_validate(customer)


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: uuid.UUID, session: SessionDep, context: TenantContextDep
) -> None:
    customer = await customers_service.get_customer(session, context.tenant_id, customer_id)
    if customer is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    await customers_service.delete_customer(session, customer)
    await commit_and_keep_tenant_context(session)
