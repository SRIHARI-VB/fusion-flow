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

from fusionflow.db import models as _models  # noqa: F401 - registers every ORM model (see main.py's own import)
from fusionflow.db.session import async_session_factory
from fusionflow.modules.connectors.cloudflare_r2.adapter import CONFIG_SCHEMA as R2_CONFIG_SCHEMA
from fusionflow.modules.connectors.facebook.adapter import CONFIG_SCHEMA as FACEBOOK_CONFIG_SCHEMA
from fusionflow.modules.connectors.gmail.adapter import CONFIG_SCHEMA as GMAIL_CONFIG_SCHEMA
from fusionflow.modules.connectors.google_calendar.adapter import CONFIG_SCHEMA as GOOGLE_CALENDAR_CONFIG_SCHEMA
from fusionflow.modules.connectors.google_meet.adapter import CONFIG_SCHEMA as GOOGLE_MEET_CONFIG_SCHEMA
from fusionflow.modules.connectors.google_sheets.adapter import CONFIG_SCHEMA as GOOGLE_SHEETS_CONFIG_SCHEMA
from fusionflow.modules.connectors.instagram.adapter import CONFIG_SCHEMA as INSTAGRAM_CONFIG_SCHEMA
from fusionflow.modules.connectors.models import ConnectorCategory, ConnectorType
from fusionflow.modules.connectors.razorpay.adapter import CONFIG_SCHEMA as RAZORPAY_CONFIG_SCHEMA
from fusionflow.modules.connectors.telegram.adapter import CONFIG_SCHEMA as TELEGRAM_CONFIG_SCHEMA
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
    {
        "key": "cloudflare_r2",
        "category": ConnectorCategory.STORAGE,
        "display_name": "Cloudflare R2",
        "config_schema": R2_CONFIG_SCHEMA,
        "oauth": False,
    },
    {
        "key": "instagram",
        "category": ConnectorCategory.SOCIAL,
        "display_name": "Instagram",
        "config_schema": INSTAGRAM_CONFIG_SCHEMA,
        "oauth": False,
    },
    {
        "key": "google_calendar",
        "category": ConnectorCategory.CALENDAR,
        "display_name": "Google Calendar",
        "config_schema": GOOGLE_CALENDAR_CONFIG_SCHEMA,
        "oauth": True,
    },
    {
        "key": "gmail",
        "category": ConnectorCategory.MAIL,
        "display_name": "Gmail",
        "config_schema": GMAIL_CONFIG_SCHEMA,
        "oauth": True,
    },
    {
        "key": "google_meet",
        "category": ConnectorCategory.VIDEO,
        "display_name": "Google Meet",
        "config_schema": GOOGLE_MEET_CONFIG_SCHEMA,
        "oauth": True,
    },
    {
        "key": "google_sheets",
        "category": ConnectorCategory.SPREADSHEET,
        "display_name": "Google Sheets",
        "config_schema": GOOGLE_SHEETS_CONFIG_SCHEMA,
        "oauth": True,
    },
    {
        "key": "telegram",
        "category": ConnectorCategory.MESSAGING,
        "display_name": "Telegram",
        "config_schema": TELEGRAM_CONFIG_SCHEMA,
        "oauth": False,
    },
    {
        "key": "facebook",
        "category": ConnectorCategory.MESSAGING,
        "display_name": "Facebook",
        "config_schema": FACEBOOK_CONFIG_SCHEMA,
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
