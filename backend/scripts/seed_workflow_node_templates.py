"""Seed the `workflow_node_templates` catalog — Part D's proof that a new
integration capability can become a palette entry as pure admin data
entry, no deploy. Idempotent - matches on `key` and updates in place, safe
to re-run after editing `TEMPLATES` below.

Two starter templates, both proven live end-to-end as part of Phase 4's
proof-of-concept (see this phase's plan section, Part E):

* `send_whatsapp_template_message` re-expresses the already-tested
  `send_whatsapp_message` bespoke node as a `connector.action` template -
  proves the migration path from a bespoke node to the generic-executor +
  template layer on a real, already-shipped capability rather than a
  synthetic one.
* `http_get_test_endpoint` is a `http.request` template against a
  harmless public test endpoint (httpbin.org) - proves a brand-new,
  code-free integration end-to-end.

Usage:
    python scripts/seed_workflow_node_templates.py
"""

from __future__ import annotations

import asyncio

from fusionflow.db.session import async_session_factory
from fusionflow.modules.admin import service as admin_service

TEMPLATES: list[dict] = [
    {
        "key": "send_whatsapp_template_message",
        # Distinct from the bespoke `send_whatsapp_message` node's own
        # "Send WhatsApp Message" label (Phase 5 palette-cleanup fix) - this
        # entry wraps the generic `connector.action` executor instead, and
        # the two rendering with the literal same label made them
        # indistinguishable in the palette.
        "label": "Send WhatsApp Message (Generic Action)",
        "description": "Sends an outbound WhatsApp text message through a connected WhatsApp connector instance.",
        "category": "Messages",
        "base_node_type": "connector.action",
        "icon": "message-circle",
        "default_config": {"action": "send_text_message"},
        "config_schema_overrides": None,
        "is_active": True,
        "required_connector_type_key": "whatsapp",
    },
    {
        "key": "http_get_test_endpoint",
        "label": "HTTP GET (test endpoint)",
        "description": "Calls a harmless public test endpoint (httpbin.org) - a starting point for wiring up a real third-party API with zero code changes.",
        "category": "Integrations",
        "base_node_type": "http.request",
        "icon": "globe",
        "default_config": {"method": "GET", "url": "https://httpbin.org/get"},
        "config_schema_overrides": None,
        "is_active": True,
        "required_connector_type_key": None,
    },
]


async def seed() -> None:
    async with async_session_factory() as session:
        existing_by_key = {t.key: t for t in await admin_service.list_workflow_node_templates(session)}
        for spec in TEMPLATES:
            existing = existing_by_key.get(spec["key"])
            if existing is not None:
                await admin_service.update_workflow_node_template(
                    session,
                    existing.id,
                    label=spec["label"],
                    description=spec["description"],
                    category=spec["category"],
                    icon=spec["icon"],
                    default_config=spec["default_config"],
                    config_schema_overrides=spec["config_schema_overrides"],
                    is_active=spec["is_active"],
                    required_connector_type_key=spec["required_connector_type_key"],
                )
                print(f"updated: {spec['key']}")
                continue
            await admin_service.create_workflow_node_template(
                session,
                key=spec["key"],
                label=spec["label"],
                description=spec["description"],
                category=spec["category"],
                base_node_type=spec["base_node_type"],
                icon=spec["icon"],
                default_config=spec["default_config"],
                config_schema_overrides=spec["config_schema_overrides"],
                is_active=spec["is_active"],
                required_connector_type_key=spec["required_connector_type_key"],
            )
            print(f"created: {spec['key']}")
        await session.commit()


if __name__ == "__main__":
    asyncio.run(seed())
