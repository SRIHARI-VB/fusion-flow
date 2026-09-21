"""Customer domain logic.

None of these functions commit — routers own the transaction boundary (see
`modules/auth/service.py` for the same convention).

Every query filters explicitly on `tenant_id` in addition to relying on
Postgres RLS (`SET LOCAL app.current_tenant_id`, applied by
`get_tenant_context`). The explicit filter is defense-in-depth, not the
primary isolation mechanism — see the plan's Risk #2 on `SET LOCAL`.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.custom_fields.validation import CustomFieldValidationError, validate_custom_fields
from fusionflow.modules.customers.models import Customer, CustomerFieldDefinition
from fusionflow.modules.customers.schemas import CustomerCreate, CustomerUpdate


async def list_field_definitions(
    session: AsyncSession, tenant_id: uuid.UUID
) -> Sequence[CustomerFieldDefinition]:
    stmt = (
        select(CustomerFieldDefinition)
        .where(CustomerFieldDefinition.tenant_id == tenant_id)
        .order_by(CustomerFieldDefinition.sort_order, CustomerFieldDefinition.key)
    )
    return (await session.execute(stmt)).scalars().all()


def _validate_customer_custom_fields(
    field_defs: Sequence[CustomerFieldDefinition], payload: dict[str, Any] | None
) -> dict[str, Any]:
    """Write-path guard for `Customer.custom_fields`, mirroring
    `catalog.service.validate_entity_custom_fields` /
    `business_objects.service.validate_record_payload`: reuses
    `custom_fields.validation.validate_custom_fields` directly since it's
    duck-typed against `.key`/`.field_type`/`.required`/`.options` and
    `CustomerFieldDefinition` has that exact shape. This is the fix for the
    gap `customers` previously had - `custom_fields` used to be stored
    unvalidated because `EntityType` (the catalog module's closed enum) has
    no `CUSTOMER` member to register against.
    """
    try:
        return validate_custom_fields(list(field_defs), payload)
    except CustomFieldValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "custom_fields validation failed", "errors": exc.errors},
        ) from exc


async def list_customers(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    name_search: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    external_ref: str | None = None,
    limit: int | None = None,
) -> list[Customer]:
    stmt = select(Customer).where(Customer.tenant_id == tenant_id)
    if name_search is not None:
        stmt = stmt.where(Customer.name.ilike(f"%{name_search}%"))
    if email is not None:
        stmt = stmt.where(Customer.email == email)
    if phone is not None:
        stmt = stmt.where(Customer.phone == phone)
    if external_ref is not None:
        stmt = stmt.where(Customer.external_ref == external_ref)
    stmt = stmt.order_by(Customer.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    rows = await session.execute(stmt)
    return list(rows.scalars().all())


async def count_customers(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Customer).where(Customer.tenant_id == tenant_id)
    return (await session.execute(stmt)).scalar_one()


async def get_customer(
    session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID
) -> Customer | None:
    return (
        await session.execute(
            select(Customer).where(Customer.id == customer_id, Customer.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def get_customer_by_phone(
    session: AsyncSession, tenant_id: uuid.UUID, phone: str
) -> Customer | None:
    """Exact-match lookup by phone number.

    Used by the `customers.find_by_phone` workflow query node and by
    `whatsapp.find_or_create_customer` (a WhatsApp payload's `from` field is
    the natural bridge between an inbound message and a `Customer` row).
    """
    return (
        await session.execute(
            select(Customer).where(Customer.phone == phone, Customer.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def create_customer(
    session: AsyncSession, tenant_id: uuid.UUID, payload: CustomerCreate
) -> Customer:
    field_defs = await list_field_definitions(session, tenant_id)
    customer = Customer(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        external_ref=payload.external_ref,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        custom_fields=_validate_customer_custom_fields(field_defs, payload.custom_fields),
    )
    session.add(customer)
    await session.flush()
    return customer


async def update_customer(
    session: AsyncSession, customer: Customer, payload: CustomerUpdate
) -> Customer:
    """Apply a partial update in place. Does not commit."""
    if payload.external_ref is not None:
        customer.external_ref = payload.external_ref
    if payload.name is not None:
        customer.name = payload.name
    if payload.email is not None:
        customer.email = payload.email
    if payload.phone is not None:
        customer.phone = payload.phone
    if payload.custom_fields is not None:
        field_defs = await list_field_definitions(session, customer.tenant_id)
        customer.custom_fields = _validate_customer_custom_fields(field_defs, payload.custom_fields)
    await session.flush()
    return customer


async def delete_customer(session: AsyncSession, customer: Customer) -> None:
    await session.delete(customer)
    await session.flush()
