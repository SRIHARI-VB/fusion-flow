"""Seed global `field_templates` rows.

Run with the backend's virtualenv active (`pip install -e ".[dev]"` per
backend/README.md) so `fusionflow` is importable, against a Postgres that
already has `alembic upgrade head` applied:

    python backend/scripts/seed_templates.py

Idempotent: matches on `(vertical, entity_type, name)` and skips anything
already present instead of duplicating it, so it is safe to re-run (e.g.
after adding a new template to `TEMPLATES` below) without creating
duplicate rows.
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from fusionflow.db.session import async_session_factory
from fusionflow.modules.custom_fields.models import EntityType, FieldTemplate, FieldType

TEMPLATES: list[dict] = [
    {
        "vertical": "retail",
        "entity_type": EntityType.PRODUCT,
        "name": "Retail product basics",
        "fields": [
            {
                "key": "sku",
                "label": "SKU",
                "field_type": FieldType.TEXT.value,
                "required": True,
                "sort_order": 0,
            },
            {
                "key": "stock_quantity",
                "label": "Stock quantity",
                "field_type": FieldType.NUMBER.value,
                "required": True,
                "sort_order": 1,
            },
            {
                "key": "size",
                "label": "Size",
                "field_type": FieldType.SELECT.value,
                "options": ["XS", "S", "M", "L", "XL"],
                "required": False,
                "sort_order": 2,
            },
        ],
    },
    {
        "vertical": "salon",
        "entity_type": EntityType.SERVICE,
        "name": "Salon service basics",
        "fields": [
            {
                "key": "duration_minutes",
                "label": "Duration (minutes)",
                "field_type": FieldType.NUMBER.value,
                "required": True,
                "sort_order": 0,
            },
            {
                "key": "requires_appointment",
                "label": "Requires appointment",
                "field_type": FieldType.BOOLEAN.value,
                "required": True,
                "sort_order": 1,
            },
            {
                "key": "stylist_notes",
                "label": "Stylist notes",
                "field_type": FieldType.RICHTEXT.value,
                "required": False,
                "sort_order": 2,
            },
        ],
    },
]


async def seed() -> None:
    async with async_session_factory() as session:
        for spec in TEMPLATES:
            existing = (
                await session.execute(
                    select(FieldTemplate).where(
                        FieldTemplate.vertical == spec["vertical"],
                        FieldTemplate.entity_type == spec["entity_type"],
                        FieldTemplate.name == spec["name"],
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                print(f"skip (already seeded): {spec['vertical']}/{spec['entity_type'].value} - {spec['name']}")
                continue
            session.add(
                FieldTemplate(
                    id=uuid.uuid4(),
                    vertical=spec["vertical"],
                    entity_type=spec["entity_type"],
                    is_global=True,
                    name=spec["name"],
                    version=1,
                    fields=spec["fields"],
                )
            )
            print(f"seeded: {spec['vertical']}/{spec['entity_type'].value} - {spec['name']}")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
