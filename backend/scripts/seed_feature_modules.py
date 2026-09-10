"""Seed the fixed-feature-module rows in the `connector_types` catalog.

Part of the "everything is a connector" unification: products, services,
coupons, offers, customers, orders, payments, tickets, kb, custom_fields,
workflows, and support_agent now live in the same global catalog table as
WhatsApp/Razorpay, tagged `category=FEATURE` (no OAuth, no adapter, no
`ConnectorInstance` state machine - entitlement alone gates their routes,
see `modules.connectors.deps.require_module_access`). Kept as a separate
script from `seed_connector_types.py` rather than merged into it: one list
is "external providers with adapters," the other is "fixed modules" -
different concerns even though they write to the same table. Idempotent -
safe to re-run after editing `FEATURE_MODULES` below.

Usage:
    python scripts/seed_feature_modules.py
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from fusionflow.db.session import async_session_factory
from fusionflow.modules.connectors.models import ConnectorCategory, ConnectorType

FEATURE_MODULES = [
    {"key": "products", "display_name": "Products"},
    {"key": "services", "display_name": "Services"},
    {"key": "coupons", "display_name": "Coupons"},
    {"key": "offers", "display_name": "Offers"},
    {"key": "customers", "display_name": "Customers"},
    {"key": "orders", "display_name": "Orders"},
    {"key": "payments", "display_name": "Payments"},
    {"key": "tickets", "display_name": "Tickets"},
    {"key": "kb", "display_name": "Knowledge Base"},
    {"key": "custom_fields", "display_name": "Custom Fields"},
    {"key": "workflows", "display_name": "Workflows"},
    {"key": "support_agent", "display_name": "Support Agent"},
]


async def seed() -> None:
    async with async_session_factory() as session:
        for spec in FEATURE_MODULES:
            existing = (
                await session.execute(select(ConnectorType).where(ConnectorType.key == spec["key"]))
            ).scalar_one_or_none()
            if existing is not None:
                existing.category = ConnectorCategory.FEATURE
                existing.display_name = spec["display_name"]
                existing.config_schema = {}
                existing.oauth = False
                existing.is_enabled_globally = True
                print(f"updated: {spec['key']}")
                continue
            session.add(
                ConnectorType(
                    id=uuid.uuid4(),
                    key=spec["key"],
                    category=ConnectorCategory.FEATURE,
                    display_name=spec["display_name"],
                    config_schema={},
                    oauth=False,
                    is_enabled_globally=True,
                )
            )
            print(f"created: {spec['key']}")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
