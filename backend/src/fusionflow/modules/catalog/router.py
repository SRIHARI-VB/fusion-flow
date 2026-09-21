"""`/api/v1/{products,services,coupons,offers}` — catalog CRUD.

Not mounted here: per the wave's coordination rules, `api.py`
(`/api/v1` router group) is owned by another agent's pass. Mount as:

    from fusionflow.modules.catalog.router import (
        coupons_router,
        offers_router,
        products_router,
        services_router,
    )
    api_router.include_router(products_router)
    api_router.include_router(services_router)
    api_router.include_router(coupons_router)
    api_router.include_router(offers_router)

Design note (products/services one-router-vs-two): `products_services` is
one table discriminated by `entity_type`, but it is exposed as two routers
(`products_router`, `services_router`) rather than one shared
`/products-services?entity_type=` router, so `/products` and `/services`
stay independent REST resources with their own tags/operation ids -
consistent with how every other resource in the API route grouping
(customers, orders, tickets, ...) gets its own top-level noun. Both routers
call the exact same `catalog.service` functions underneath with
`entity_type` pinned by `_build_product_service_router`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from fusionflow.core.deps import SessionDep, TenantContextDep
from fusionflow.db.session import commit_and_keep_tenant_context
from fusionflow.modules.catalog import service as catalog_service
from fusionflow.modules.connectors.deps import enforce_resource_limit, require_module_access
from fusionflow.modules.catalog.models import ProductServiceType
from fusionflow.modules.catalog.schemas import (
    CouponCreate,
    CouponOut,
    CouponUpdate,
    OfferCreate,
    OfferOut,
    OfferUpdate,
    ProductServiceCreate,
    ProductServiceOut,
    ProductServiceUpdate,
)
from fusionflow.modules.custom_fields.models import EntityType

_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def _build_product_service_router(
    *, entity_type: ProductServiceType, prefix: str, tag: str, module_key: str
) -> APIRouter:
    custom_field_entity_type = EntityType(entity_type.value)
    router = APIRouter(
        prefix=prefix,
        tags=[tag],
        dependencies=[Depends(require_module_access(module_key))],
    )

    async def _count_fn(session, tenant_id):
        return await catalog_service.count_products_services(session, tenant_id, entity_type=entity_type)

    _resource_gate = Depends(enforce_resource_limit(module_key, _count_fn))

    @router.get("", response_model=list[ProductServiceOut])
    async def list_items(context: TenantContextDep, session: SessionDep) -> list[ProductServiceOut]:
        items = await catalog_service.list_products_services(
            session, tenant_id=context.tenant_id, entity_type=entity_type
        )
        return [ProductServiceOut.model_validate(item) for item in items]

    @router.post("", response_model=ProductServiceOut, status_code=status.HTTP_201_CREATED)
    async def create_item(
        payload: ProductServiceCreate, context: TenantContextDep, session: SessionDep, _gate=_resource_gate
    ) -> ProductServiceOut:
        if payload.entity_type != entity_type:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"entity_type must be '{entity_type.value}' on {prefix}",
            )
        custom_fields = await catalog_service.validate_entity_custom_fields(
            session,
            tenant_id=context.tenant_id,
            entity_type=custom_field_entity_type,
            payload=payload.custom_fields,
        )
        item = await catalog_service.create_product_service(
            session, tenant_id=context.tenant_id, payload=payload, custom_fields=custom_fields
        )
        await commit_and_keep_tenant_context(session)
        return ProductServiceOut.model_validate(item)

    @router.get("/{item_id}", response_model=ProductServiceOut)
    async def get_item(item_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> ProductServiceOut:
        item = await catalog_service.get_product_service(session, tenant_id=context.tenant_id, item_id=item_id)
        if item is None or item.entity_type != entity_type:
            raise _NOT_FOUND
        return ProductServiceOut.model_validate(item)

    @router.patch("/{item_id}", response_model=ProductServiceOut)
    async def update_item(
        item_id: uuid.UUID, payload: ProductServiceUpdate, context: TenantContextDep, session: SessionDep
    ) -> ProductServiceOut:
        item = await catalog_service.get_product_service(session, tenant_id=context.tenant_id, item_id=item_id)
        if item is None or item.entity_type != entity_type:
            raise _NOT_FOUND
        custom_fields = None
        if payload.custom_fields is not None:
            custom_fields = await catalog_service.validate_entity_custom_fields(
                session,
                tenant_id=context.tenant_id,
                entity_type=custom_field_entity_type,
                payload=payload.custom_fields,
            )
        item = await catalog_service.update_product_service(session, item, payload, custom_fields)
        await commit_and_keep_tenant_context(session)
        # `updated_at` is DB-computed (`onupdate=func.now()`) and left
        # expired after an UPDATE flush - see
        # `predefined_automations/router.py`'s identical fix for the full
        # explanation of the MissingGreenlet crash this avoids.
        await session.refresh(item, attribute_names=["updated_at"])
        return ProductServiceOut.model_validate(item)

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_item(item_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> None:
        item = await catalog_service.get_product_service(session, tenant_id=context.tenant_id, item_id=item_id)
        if item is None or item.entity_type != entity_type:
            raise _NOT_FOUND
        await catalog_service.delete_product_service(session, item)
        await commit_and_keep_tenant_context(session)

    return router


products_router = _build_product_service_router(
    entity_type=ProductServiceType.PRODUCT, prefix="/products", tag="products", module_key="products"
)
services_router = _build_product_service_router(
    entity_type=ProductServiceType.SERVICE, prefix="/services", tag="services", module_key="services"
)

coupons_router = APIRouter(
    prefix="/coupons",
    tags=["coupons"],
    dependencies=[Depends(require_module_access("coupons"))],
)
offers_router = APIRouter(
    prefix="/offers",
    tags=["offers"],
    dependencies=[Depends(require_module_access("offers"))],
)
_coupons_resource_gate = Depends(enforce_resource_limit("coupons", catalog_service.count_coupons))
_offers_resource_gate = Depends(enforce_resource_limit("offers", catalog_service.count_offers))


# ---------------------------------------------------------------------------
# Coupons
# ---------------------------------------------------------------------------


@coupons_router.get("", response_model=list[CouponOut])
async def list_coupons(context: TenantContextDep, session: SessionDep) -> list[CouponOut]:
    coupons = await catalog_service.list_coupons(session, tenant_id=context.tenant_id)
    return [CouponOut.model_validate(c) for c in coupons]


@coupons_router.post("", response_model=CouponOut, status_code=status.HTTP_201_CREATED)
async def create_coupon(
    payload: CouponCreate, context: TenantContextDep, session: SessionDep, _gate=_coupons_resource_gate
) -> CouponOut:
    custom_fields = await catalog_service.validate_entity_custom_fields(
        session, tenant_id=context.tenant_id, entity_type=EntityType.COUPON, payload=payload.custom_fields
    )
    coupon = await catalog_service.create_coupon(
        session, tenant_id=context.tenant_id, payload=payload, custom_fields=custom_fields
    )
    await commit_and_keep_tenant_context(session)
    return CouponOut.model_validate(coupon)


@coupons_router.get("/{coupon_id}", response_model=CouponOut)
async def get_coupon(coupon_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> CouponOut:
    coupon = await catalog_service.get_coupon(session, tenant_id=context.tenant_id, coupon_id=coupon_id)
    if coupon is None:
        raise _NOT_FOUND
    return CouponOut.model_validate(coupon)


@coupons_router.patch("/{coupon_id}", response_model=CouponOut)
async def update_coupon(
    coupon_id: uuid.UUID, payload: CouponUpdate, context: TenantContextDep, session: SessionDep
) -> CouponOut:
    coupon = await catalog_service.get_coupon(session, tenant_id=context.tenant_id, coupon_id=coupon_id)
    if coupon is None:
        raise _NOT_FOUND
    custom_fields = None
    if payload.custom_fields is not None:
        custom_fields = await catalog_service.validate_entity_custom_fields(
            session, tenant_id=context.tenant_id, entity_type=EntityType.COUPON, payload=payload.custom_fields
        )
    coupon = await catalog_service.update_coupon(session, coupon, payload, custom_fields)
    await commit_and_keep_tenant_context(session)
    # Same `updated_at` refresh as `update_item` above.
    await session.refresh(coupon, attribute_names=["updated_at"])
    return CouponOut.model_validate(coupon)


@coupons_router.delete("/{coupon_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_coupon(coupon_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> None:
    coupon = await catalog_service.get_coupon(session, tenant_id=context.tenant_id, coupon_id=coupon_id)
    if coupon is None:
        raise _NOT_FOUND
    await catalog_service.delete_coupon(session, coupon)
    await commit_and_keep_tenant_context(session)


# ---------------------------------------------------------------------------
# Offers
# ---------------------------------------------------------------------------


@offers_router.get("", response_model=list[OfferOut])
async def list_offers(context: TenantContextDep, session: SessionDep) -> list[OfferOut]:
    offers = await catalog_service.list_offers(session, tenant_id=context.tenant_id)
    return [OfferOut.model_validate(o) for o in offers]


@offers_router.post("", response_model=OfferOut, status_code=status.HTTP_201_CREATED)
async def create_offer(
    payload: OfferCreate, context: TenantContextDep, session: SessionDep, _gate=_offers_resource_gate
) -> OfferOut:
    custom_fields = await catalog_service.validate_entity_custom_fields(
        session, tenant_id=context.tenant_id, entity_type=EntityType.OFFER, payload=payload.custom_fields
    )
    offer = await catalog_service.create_offer(
        session, tenant_id=context.tenant_id, payload=payload, custom_fields=custom_fields
    )
    await commit_and_keep_tenant_context(session)
    return OfferOut.model_validate(offer)


@offers_router.get("/{offer_id}", response_model=OfferOut)
async def get_offer(offer_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> OfferOut:
    offer = await catalog_service.get_offer(session, tenant_id=context.tenant_id, offer_id=offer_id)
    if offer is None:
        raise _NOT_FOUND
    return OfferOut.model_validate(offer)


@offers_router.patch("/{offer_id}", response_model=OfferOut)
async def update_offer(
    offer_id: uuid.UUID, payload: OfferUpdate, context: TenantContextDep, session: SessionDep
) -> OfferOut:
    offer = await catalog_service.get_offer(session, tenant_id=context.tenant_id, offer_id=offer_id)
    if offer is None:
        raise _NOT_FOUND
    custom_fields = None
    if payload.custom_fields is not None:
        custom_fields = await catalog_service.validate_entity_custom_fields(
            session, tenant_id=context.tenant_id, entity_type=EntityType.OFFER, payload=payload.custom_fields
        )
    offer = await catalog_service.update_offer(session, offer, payload, custom_fields)
    await commit_and_keep_tenant_context(session)
    # Same `updated_at` refresh as `update_item` above.
    await session.refresh(offer, attribute_names=["updated_at"])
    return OfferOut.model_validate(offer)


@offers_router.delete("/{offer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_offer(offer_id: uuid.UUID, context: TenantContextDep, session: SessionDep) -> None:
    offer = await catalog_service.get_offer(session, tenant_id=context.tenant_id, offer_id=offer_id)
    if offer is None:
        raise _NOT_FOUND
    await catalog_service.delete_offer(session, offer)
    await commit_and_keep_tenant_context(session)
