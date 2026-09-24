"""Catalog domain logic: products/services, coupons, offers.

None of these functions commit - routers own the transaction boundary, same
convention as `modules/tenancy/service.py` and `modules/custom_fields/service.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Sequence

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.catalog.models import Coupon, Offer, ProductService, ProductServiceType
from fusionflow.modules.catalog.schemas import (
    CouponCreate,
    CouponUpdate,
    OfferCreate,
    OfferUpdate,
    ProductServiceCreate,
    ProductServiceUpdate,
)
from fusionflow.modules.custom_fields import service as custom_fields_service
from fusionflow.modules.custom_fields.models import EntityType
from fusionflow.modules.custom_fields.validation import CustomFieldValidationError, validate_custom_fields


async def validate_entity_custom_fields(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_type: EntityType,
    payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Shared write-path guard for every catalog table's `custom_fields` column.

    Loads the tenant's live `field_definitions` for `entity_type` and
    validates/normalizes `payload` against them, raising an HTTP 422 with
    field-level errors instead of ever persisting an unvalidated JSONB blob.
    Reused by products, services, coupons and offers (see router.py).
    """
    definitions = await custom_fields_service.list_field_definitions(
        session, tenant_id=tenant_id, entity_type=entity_type
    )
    try:
        return validate_custom_fields(list(definitions), payload)
    except CustomFieldValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "custom_fields validation failed", "errors": exc.errors},
        ) from exc


# ---------------------------------------------------------------------------
# ProductService
# ---------------------------------------------------------------------------


async def list_products_services(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    entity_type: ProductServiceType | None = None,
    name_search: str | None = None,
    is_active: bool | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    limit: int | None = None,
) -> Sequence[ProductService]:
    stmt = select(ProductService).where(ProductService.tenant_id == tenant_id)
    if entity_type is not None:
        stmt = stmt.where(ProductService.entity_type == entity_type)
    if name_search is not None:
        stmt = stmt.where(ProductService.name.ilike(f"%{name_search}%"))
    if is_active is not None:
        stmt = stmt.where(ProductService.is_active == is_active)
    if min_price is not None:
        stmt = stmt.where(ProductService.base_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(ProductService.base_price <= max_price)
    stmt = stmt.order_by(ProductService.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return (await session.execute(stmt)).scalars().all()


async def count_products_services(
    session: AsyncSession, tenant_id: uuid.UUID, *, entity_type: ProductServiceType
) -> int:
    """Used by `enforce_resource_limit("products"/"services", ...)` -
    `entity_type` is bound at router-registration time via `functools.partial`
    or a small closure (see `catalog/router.py`'s `_build_product_service_router`),
    matching how that factory already binds `module_key` per router."""
    stmt = select(func.count()).select_from(ProductService).where(
        ProductService.tenant_id == tenant_id, ProductService.entity_type == entity_type
    )
    return (await session.execute(stmt)).scalar_one()


async def get_product_service(
    session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
) -> ProductService | None:
    return (
        await session.execute(
            select(ProductService).where(ProductService.id == item_id, ProductService.tenant_id == tenant_id)
        )
    ).scalar_one_or_none()


async def create_product_service(
    session: AsyncSession, *, tenant_id: uuid.UUID, payload: ProductServiceCreate, custom_fields: dict[str, Any]
) -> ProductService:
    item = ProductService(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        entity_type=payload.entity_type,
        name=payload.name,
        description=payload.description,
        base_price=payload.base_price,
        is_active=payload.is_active,
        custom_fields=custom_fields,
    )
    session.add(item)
    await session.flush()
    return item


async def update_product_service(
    session: AsyncSession,
    item: ProductService,
    payload: ProductServiceUpdate,
    custom_fields: dict[str, Any] | None,
) -> ProductService:
    if payload.name is not None:
        item.name = payload.name
    if payload.description is not None:
        item.description = payload.description
    if payload.base_price is not None:
        item.base_price = payload.base_price
    if payload.is_active is not None:
        item.is_active = payload.is_active
    if custom_fields is not None:
        item.custom_fields = custom_fields
    await session.flush()
    return item


async def delete_product_service(session: AsyncSession, item: ProductService) -> None:
    await session.delete(item)
    await session.flush()


# ---------------------------------------------------------------------------
# Coupon
# ---------------------------------------------------------------------------


async def list_coupons(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    code_search: str | None = None,
    valid_now: bool | None = None,
    limit: int | None = None,
) -> Sequence[Coupon]:
    stmt = select(Coupon).where(Coupon.tenant_id == tenant_id)
    if code_search is not None:
        stmt = stmt.where(Coupon.code.ilike(f"%{code_search}%"))
    if valid_now is not None:
        now = func.now()
        currently_valid = and_(
            or_(Coupon.valid_from.is_(None), Coupon.valid_from <= now),
            or_(Coupon.valid_to.is_(None), Coupon.valid_to >= now),
        )
        stmt = stmt.where(currently_valid if valid_now else ~currently_valid)
    stmt = stmt.order_by(Coupon.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return (await session.execute(stmt)).scalars().all()


async def count_coupons(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Coupon).where(Coupon.tenant_id == tenant_id)
    return (await session.execute(stmt)).scalar_one()


async def get_coupon(session: AsyncSession, *, tenant_id: uuid.UUID, coupon_id: uuid.UUID) -> Coupon | None:
    return (
        await session.execute(select(Coupon).where(Coupon.id == coupon_id, Coupon.tenant_id == tenant_id))
    ).scalar_one_or_none()


async def create_coupon(
    session: AsyncSession, *, tenant_id: uuid.UUID, payload: CouponCreate, custom_fields: dict[str, Any]
) -> Coupon:
    coupon = Coupon(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code=payload.code,
        discount_type=payload.discount_type,
        discount_value=payload.discount_value,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        usage_limit=payload.usage_limit,
        applies_to=payload.applies_to,
        custom_fields=custom_fields,
    )
    session.add(coupon)
    await session.flush()
    return coupon


async def update_coupon(
    session: AsyncSession, coupon: Coupon, payload: CouponUpdate, custom_fields: dict[str, Any] | None
) -> Coupon:
    if payload.discount_type is not None:
        coupon.discount_type = payload.discount_type
    if payload.discount_value is not None:
        coupon.discount_value = payload.discount_value
    if payload.valid_from is not None:
        coupon.valid_from = payload.valid_from
    if payload.valid_to is not None:
        coupon.valid_to = payload.valid_to
    if payload.usage_limit is not None:
        coupon.usage_limit = payload.usage_limit
    if payload.applies_to is not None:
        coupon.applies_to = payload.applies_to
    if custom_fields is not None:
        coupon.custom_fields = custom_fields
    await session.flush()
    return coupon


async def delete_coupon(session: AsyncSession, coupon: Coupon) -> None:
    await session.delete(coupon)
    await session.flush()


# ---------------------------------------------------------------------------
# Offer
# ---------------------------------------------------------------------------


async def list_offers(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    valid_now: bool | None = None,
    limit: int | None = None,
) -> Sequence[Offer]:
    stmt = select(Offer).where(Offer.tenant_id == tenant_id)
    if valid_now is not None:
        now = func.now()
        currently_valid = and_(
            or_(Offer.active_from.is_(None), Offer.active_from <= now),
            or_(Offer.active_to.is_(None), Offer.active_to >= now),
        )
        stmt = stmt.where(currently_valid if valid_now else ~currently_valid)
    stmt = stmt.order_by(Offer.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return (await session.execute(stmt)).scalars().all()


async def count_offers(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    stmt = select(func.count()).select_from(Offer).where(Offer.tenant_id == tenant_id)
    return (await session.execute(stmt)).scalar_one()


async def get_offer(session: AsyncSession, *, tenant_id: uuid.UUID, offer_id: uuid.UUID) -> Offer | None:
    return (
        await session.execute(select(Offer).where(Offer.id == offer_id, Offer.tenant_id == tenant_id))
    ).scalar_one_or_none()


async def create_offer(
    session: AsyncSession, *, tenant_id: uuid.UUID, payload: OfferCreate, custom_fields: dict[str, Any]
) -> Offer:
    offer = Offer(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=payload.name,
        applies_to=payload.applies_to,
        active_from=payload.active_from,
        active_to=payload.active_to,
        custom_fields=custom_fields,
    )
    session.add(offer)
    await session.flush()
    return offer


async def update_offer(
    session: AsyncSession, offer: Offer, payload: OfferUpdate, custom_fields: dict[str, Any] | None
) -> Offer:
    if payload.name is not None:
        offer.name = payload.name
    if payload.applies_to is not None:
        offer.applies_to = payload.applies_to
    if payload.active_from is not None:
        offer.active_from = payload.active_from
    if payload.active_to is not None:
        offer.active_to = payload.active_to
    if custom_fields is not None:
        offer.custom_fields = custom_fields
    await session.flush()
    return offer


async def delete_offer(session: AsyncSession, offer: Offer) -> None:
    await session.delete(offer)
    await session.flush()


# ---------------------------------------------------------------------------
# Cross-entity discount lookup (coupons + offers)
# ---------------------------------------------------------------------------


def _applies_to_target(applies_to: dict[str, Any], *, service_id: uuid.UUID | None, product_id: uuid.UUID | None) -> bool:
    """`applies_to` round-trips UUIDs as strings via JSONB, so compare as strings."""
    service_ids = {str(v) for v in applies_to.get("service_ids", [])}
    product_ids = {str(v) for v in applies_to.get("product_ids", [])}
    if service_id is not None and str(service_id) in service_ids:
        return True
    if product_id is not None and str(product_id) in product_ids:
        return True
    return False


async def get_active_discounts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    service_id: uuid.UUID | None = None,
    product_id: uuid.UUID | None = None,
) -> list[dict[str, Any]]:
    """Coupons + offers currently active for the tenant and scoped (via
    `applies_to`) to the given service/product, if either is passed.

    Used by a workflow node (see `workflow_adapter.py`/nodes registry in
    another agent's pass) to surface "here's a discount you qualify for"
    at run time - keep the returned dict shape stable, it's a cross-module
    contract.
    """
    now = datetime.now(timezone.utc)
    results: list[dict[str, Any]] = []

    coupons = (
        await session.execute(select(Coupon).where(Coupon.tenant_id == tenant_id))
    ).scalars().all()
    for coupon in coupons:
        if coupon.valid_from is not None and coupon.valid_from > now:
            continue
        if coupon.valid_to is not None and coupon.valid_to < now:
            continue
        if not _applies_to_target(coupon.applies_to, service_id=service_id, product_id=product_id):
            continue
        results.append(
            {
                "kind": "coupon",
                "id": str(coupon.id),
                "label": coupon.code,
                "discount_type": coupon.discount_type.value,
                "discount_value": str(coupon.discount_value),
            }
        )

    offers = (
        await session.execute(select(Offer).where(Offer.tenant_id == tenant_id))
    ).scalars().all()
    for offer in offers:
        if offer.active_from is not None and offer.active_from > now:
            continue
        if offer.active_to is not None and offer.active_to < now:
            continue
        if not _applies_to_target(offer.applies_to, service_id=service_id, product_id=product_id):
            continue
        results.append(
            {
                "kind": "offer",
                "id": str(offer.id),
                "label": offer.name,
                "discount_type": None,
                "discount_value": None,
            }
        )

    return results
