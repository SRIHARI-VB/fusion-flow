"""`ModuleQueryAdapter` registrations for `products`/`services`/`coupons`/
`offers` - see `modules/workflows/engine/module_registry.py`'s module
docstring for the architecture this fits into.

Products and services share one physical table (`ProductService`,
discriminated by `entity_type`) - hence two adapter *instances* of the same
class, one bound to `ProductServiceType.PRODUCT`, one to `.SERVICE`, mirroring
`catalog/router.py`'s existing `_build_product_service_router` factory
pattern for the same reason.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.catalog import service as catalog_service
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
from fusionflow.modules.workflows.engine.module_registry import ModuleQueryAdapter, registry


class ProductServiceQueryAdapter(ModuleQueryAdapter):
    def __init__(self, entity_type: ProductServiceType) -> None:
        self.entity_type = entity_type
        self.module_key = "products" if entity_type == ProductServiceType.PRODUCT else "services"

    async def list(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        min_price = filters.get("min_price")
        max_price = filters.get("max_price")
        items = await catalog_service.list_products_services(
            session,
            tenant_id=tenant_id,
            entity_type=self.entity_type,
            name_search=filters.get("name_search"),
            is_active=filters.get("is_active"),
            min_price=Decimal(str(min_price)) if min_price is not None else None,
            max_price=Decimal(str(max_price)) if max_price is not None else None,
            limit=limit,
        )
        return [ProductServiceOut.model_validate(item).model_dump(mode="json") for item in items]

    async def get(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> dict[str, Any] | None:
        item = await catalog_service.get_product_service(session, tenant_id=tenant_id, item_id=item_id)
        if item is None or item.entity_type != self.entity_type:
            return None
        return ProductServiceOut.model_validate(item).model_dump(mode="json")

    async def create(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any]:
        payload = ProductServiceCreate.model_validate({**fields, "entity_type": self.entity_type})
        custom_fields = await catalog_service.validate_entity_custom_fields(
            session,
            tenant_id=tenant_id,
            entity_type=EntityType(self.entity_type.value),
            payload=payload.custom_fields,
        )
        item = await catalog_service.create_product_service(
            session, tenant_id=tenant_id, payload=payload, custom_fields=custom_fields
        )
        return ProductServiceOut.model_validate(item).model_dump(mode="json")

    async def update(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        item = await catalog_service.get_product_service(session, tenant_id=tenant_id, item_id=item_id)
        if item is None or item.entity_type != self.entity_type:
            return None
        payload = ProductServiceUpdate.model_validate(fields)
        custom_fields = None
        if payload.custom_fields is not None:
            custom_fields = await catalog_service.validate_entity_custom_fields(
                session,
                tenant_id=tenant_id,
                entity_type=EntityType(self.entity_type.value),
                payload=payload.custom_fields,
            )
        updated = await catalog_service.update_product_service(session, item, payload, custom_fields)
        return ProductServiceOut.model_validate(updated).model_dump(mode="json")


class CouponsQueryAdapter(ModuleQueryAdapter):
    module_key = "coupons"

    async def list(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        items = await catalog_service.list_coupons(
            session,
            tenant_id=tenant_id,
            code_search=filters.get("code_search"),
            valid_now=filters.get("valid_now"),
            limit=limit,
        )
        return [CouponOut.model_validate(item).model_dump(mode="json") for item in items]

    async def get(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> dict[str, Any] | None:
        item = await catalog_service.get_coupon(session, tenant_id=tenant_id, coupon_id=item_id)
        return CouponOut.model_validate(item).model_dump(mode="json") if item else None

    async def create(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any]:
        payload = CouponCreate.model_validate(fields)
        custom_fields = await catalog_service.validate_entity_custom_fields(
            session, tenant_id=tenant_id, entity_type=EntityType.COUPON, payload=payload.custom_fields
        )
        item = await catalog_service.create_coupon(
            session, tenant_id=tenant_id, payload=payload, custom_fields=custom_fields
        )
        return CouponOut.model_validate(item).model_dump(mode="json")

    async def update(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        item = await catalog_service.get_coupon(session, tenant_id=tenant_id, coupon_id=item_id)
        if item is None:
            return None
        payload = CouponUpdate.model_validate(fields)
        custom_fields = None
        if payload.custom_fields is not None:
            custom_fields = await catalog_service.validate_entity_custom_fields(
                session, tenant_id=tenant_id, entity_type=EntityType.COUPON, payload=payload.custom_fields
            )
        updated = await catalog_service.update_coupon(session, item, payload, custom_fields)
        return CouponOut.model_validate(updated).model_dump(mode="json")


class OffersQueryAdapter(ModuleQueryAdapter):
    module_key = "offers"

    async def list(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        items = await catalog_service.list_offers(
            session, tenant_id=tenant_id, valid_now=filters.get("valid_now"), limit=limit
        )
        return [OfferOut.model_validate(item).model_dump(mode="json") for item in items]

    async def get(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> dict[str, Any] | None:
        item = await catalog_service.get_offer(session, tenant_id=tenant_id, offer_id=item_id)
        return OfferOut.model_validate(item).model_dump(mode="json") if item else None

    async def create(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any]:
        payload = OfferCreate.model_validate(fields)
        custom_fields = await catalog_service.validate_entity_custom_fields(
            session, tenant_id=tenant_id, entity_type=EntityType.OFFER, payload=payload.custom_fields
        )
        item = await catalog_service.create_offer(
            session, tenant_id=tenant_id, payload=payload, custom_fields=custom_fields
        )
        return OfferOut.model_validate(item).model_dump(mode="json")

    async def update(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> dict[str, Any] | None:
        item = await catalog_service.get_offer(session, tenant_id=tenant_id, offer_id=item_id)
        if item is None:
            return None
        payload = OfferUpdate.model_validate(fields)
        custom_fields = None
        if payload.custom_fields is not None:
            custom_fields = await catalog_service.validate_entity_custom_fields(
                session, tenant_id=tenant_id, entity_type=EntityType.OFFER, payload=payload.custom_fields
            )
        updated = await catalog_service.update_offer(session, item, payload, custom_fields)
        return OfferOut.model_validate(updated).model_dump(mode="json")


registry.register(ProductServiceQueryAdapter(ProductServiceType.PRODUCT))
registry.register(ProductServiceQueryAdapter(ProductServiceType.SERVICE))
registry.register(CouponsQueryAdapter())
registry.register(OffersQueryAdapter())
