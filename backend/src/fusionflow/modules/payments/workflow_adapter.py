"""`ModuleQueryAdapter` registration for `payments` - **list/get only**, no
create or update node. A payment record must only ever be created by the
real payment adapter processing a real provider webhook
(`upsert_payment_from_provider`) - a workflow-fabricated payment row would
misrepresent financial data. Deliberate, called-out exception from the
Phase 6 plan.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.payments import service as payments_service
from fusionflow.modules.payments.models import PaymentStatus
from fusionflow.modules.payments.schemas import PaymentOut
from fusionflow.modules.workflows.engine.module_registry import ModuleQueryAdapter, registry


class PaymentsQueryAdapter(ModuleQueryAdapter):
    module_key = "payments"

    async def list(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, filters: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        status_value = filters.get("status")
        order_id = filters.get("order_id")
        customer_id = filters.get("customer_id")
        items = await payments_service.list_payments(
            session,
            tenant_id,
            status=PaymentStatus(status_value) if status_value else None,
            order_id=uuid.UUID(order_id) if order_id else None,
            customer_id=uuid.UUID(customer_id) if customer_id else None,
            limit=limit,
        )
        return [PaymentOut.model_validate(item).model_dump(mode="json") for item in items]

    async def get(
        self, session: AsyncSession, *, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> dict[str, Any] | None:
        item = await payments_service.get_payment(session, tenant_id, item_id)
        return PaymentOut.model_validate(item).model_dump(mode="json") if item else None


registry.register(PaymentsQueryAdapter())
