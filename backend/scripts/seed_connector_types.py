"""Seed the `connector_types` catalog.

Found empty against the live database while manually testing the
Razorpay webhook flow: `POST /connectors/{type_key}/connect` 404s with
"Unknown or disabled connector type" for every provider, because nothing
ever inserted a row here - the WhatsApp/Razorpay adapters register
themselves into `base.registry` (in-process), but that registry and the
`connector_types` table are deliberately separate (the table is what
`GET /connectors/types` and the connect/webhook routes actually query
against; the registry is what resolves a matched row to the adapter code
that handles it). Idempotent - safe to run again after adding a new
provider.

Usage:
    python scripts/seed_connector_types.py
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from fusionflow.db.session import async_session_factory
from fusionflow.modules.connectors.models import ConnectorCategory, ConnectorType
from fusionflow.modules.connectors.razorpay.adapter import CONFIG_SCHEMA as RAZORPAY_CONFIG_SCHEMA
from fusionflow.modules.connectors.whatsapp.adapter import CONFIG_SCHEMA as WHATSAPP_CONFIG_SCHEMA

CONNECTOR_TYPES = [
    {
        "key": "whatsapp",
        "category": ConnectorCategory.MESSAGING,
        "display_name": "WhatsApp",
        "config_schema": WHATSAPP_CONFIG_SCHEMA,
        "oauth": True,
    },
    {
        "key": "razorpay",
        "category": ConnectorCategory.PAYMENT,
        "display_name": "Razorpay",
        "config_schema": RAZORPAY_CONFIG_SCHEMA,
        "oauth": False,
    },
]


async def seed() -> None:
    async with async_session_factory() as session:
        for spec in CONNECTOR_TYPES:
            existing = (
                await session.execute(select(ConnectorType).where(ConnectorType.key == spec["key"]))
            ).scalar_one_or_none()
            if existing is not None:
                existing.category = spec["category"]
                existing.display_name = spec["display_name"]
                existing.config_schema = spec["config_schema"]
                existing.oauth = spec["oauth"]
                existing.is_enabled_globally = True
                print(f"updated: {spec['key']}")
                continue
            session.add(
                ConnectorType(
                    id=uuid.uuid4(),
                    key=spec["key"],
                    category=spec["category"],
                    display_name=spec["display_name"],
                    config_schema=spec["config_schema"],
                    oauth=spec["oauth"],
                    is_enabled_globally=True,
                )
            )
            print(f"created: {spec['key']}")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
