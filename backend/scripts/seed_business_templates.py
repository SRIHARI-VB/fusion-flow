"""Seed the `business_templates` catalog (onboarding "starter kits").

Found empty against the live database while fixing the onboarding vertical
dropdown to read from the real template catalog instead of a hardcoded
frontend list: with zero rows here, `GET /api/v1/business-templates`
returns `[]` and onboarding's "Pick a starter kit" step (and now its
vertical dropdown too) has nothing to show. Idempotent - matches on `key`
and updates in place, so it is safe to re-run after editing `TEMPLATES`
below.

Usage:
    python scripts/seed_business_templates.py
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from fusionflow.db.session import async_session_factory
from fusionflow.modules.admin.models import BusinessTemplate, BusinessTemplateConnectorType
from fusionflow.modules.connectors.models import ConnectorType

TEMPLATES: list[dict] = [
    {
        "key": "retail-starter",
        "name": "Retail starter kit",
        "description": "Product catalog with SKU/stock fields, WhatsApp for order updates, Razorpay for payments.",
        "vertical": "retail",
        "connector_keys": ["whatsapp", "razorpay"],
    },
    {
        "key": "salon-starter",
        "name": "Salon & beauty starter kit",
        "description": "Service bookings with duration/appointment fields, WhatsApp for appointment reminders.",
        "vertical": "salon",
        "connector_keys": ["whatsapp"],
    },
    {
        "key": "restaurant-starter",
        "name": "Restaurant starter kit",
        "description": "WhatsApp for order-taking, Razorpay for online payments.",
        "vertical": "restaurant",
        "connector_keys": ["whatsapp", "razorpay"],
    },
]


async def seed() -> None:
    async with async_session_factory() as session:
        connector_types = {
            ct.key: ct for ct in (await session.execute(select(ConnectorType))).scalars().all()
        }

        for spec in TEMPLATES:
            missing = [k for k in spec["connector_keys"] if k not in connector_types]
            if missing:
                print(f"skip {spec['key']}: connector_types not seeded yet: {missing}")
                continue

            existing = (
                await session.execute(select(BusinessTemplate).where(BusinessTemplate.key == spec["key"]))
            ).scalar_one_or_none()

            if existing is None:
                template = BusinessTemplate(
                    id=uuid.uuid4(),
                    key=spec["key"],
                    name=spec["name"],
                    description=spec["description"],
                    vertical=spec["vertical"],
                    plan_id=None,
                    is_active=True,
                )
                session.add(template)
                await session.flush()
                print(f"created: {spec['key']}")
            else:
                template = existing
                template.name = spec["name"]
                template.description = spec["description"]
                template.vertical = spec["vertical"]
                template.is_active = True
                await session.execute(
                    BusinessTemplateConnectorType.__table__.delete().where(
                        BusinessTemplateConnectorType.business_template_id == template.id
                    )
                )
                print(f"updated: {spec['key']}")

            for connector_key in spec["connector_keys"]:
                session.add(
                    BusinessTemplateConnectorType(
                        id=uuid.uuid4(),
                        business_template_id=template.id,
                        connector_type_id=connector_types[connector_key].id,
                    )
                )

        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
