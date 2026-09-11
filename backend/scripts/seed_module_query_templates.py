"""Seed the `workflow_node_templates` catalog with one friendly palette
entry per legitimate module+operation pair, over Phase 6's 4 generic
`module.list`/`module.get`/`module.create`/`module.update` executors -
mirrors `seed_workflow_node_templates.py`'s exact idempotent
upsert-by-key pattern.

Only the operations each module's `ModuleQueryAdapter` actually supports
are seeded here (see `modules/workflows/engine/module_registry.py` and
each module's own `workflow_adapter.py`): Payments gets no create/update
row, Orders gets no create row and its update template is explicitly
"status only" - both deliberate, called-out exceptions from the Phase 6
plan, not an oversight.

Usage:
    python scripts/seed_module_query_templates.py
"""

from __future__ import annotations

import asyncio

from fusionflow.db.session import async_session_factory
from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.workflows.module_catalog import FIXED_MODULE_CATALOG

# Display metadata (label/category/icon) for every full-CRUD module now
# lives in `module_catalog.FIXED_MODULE_CATALOG` - the same source of truth
# `GET /workflows/modules` (the composable-builder redesign's unified module
# picker) reads from - so this seed script and that endpoint can never
# drift apart. Orders/payments are excluded here: they're in that same
# catalog too (for display purposes), but this script hand-writes their
# templates below since neither gets the generic full list/get/create/update
# set (see this module's docstring for why).
_FULL_CRUD_MODULES: list[dict] = [
    {"module": spec.module_key, "label": spec.label, "category": spec.category, "icon": spec.icon}
    for spec in FIXED_MODULE_CATALOG.values()
    if spec.module_key not in ("orders", "payments")
]

TEMPLATES: list[dict] = []

for spec in _FULL_CRUD_MODULES:
    module, label, category, icon = spec["module"], spec["label"], spec["category"], spec["icon"]
    # `tickets` already has a dedicated `create_ticket` bespoke node type
    # labeled "Create Ticket" (see nodes/create_ticket.py) - suffix this
    # generic-executor template's label with "Record" so the palette never
    # shows two identically-labeled entries.
    create_label = f"Create {label} Record" if module == "tickets" else f"Create {label}"
    TEMPLATES.extend(
        [
            {
                "key": f"list_{module}",
                "label": f"List {label}s",
                "description": f"Lists {label.lower()} records for this business, filtered and capped.",
                "category": category,
                "base_node_type": "module.list",
                "icon": icon,
                "default_config": {"module": module, "limit": 20},
            },
            {
                "key": f"get_{module}",
                "label": f"Get {label}",
                "description": f"Fetches a single {label.lower()} record by id.",
                "category": category,
                "base_node_type": "module.get",
                "icon": icon,
                "default_config": {"module": module},
            },
            {
                "key": f"create_{module}",
                "label": create_label,
                "description": f"Creates a new {label.lower()} record.",
                "category": category,
                "base_node_type": "module.create",
                "icon": icon,
                "default_config": {"module": module},
            },
            {
                "key": f"update_{module}",
                "label": f"Update {label}",
                "description": f"Updates an existing {label.lower()} record.",
                "category": category,
                "base_node_type": "module.update",
                "icon": icon,
                "default_config": {"module": module},
            },
        ]
    )

# Orders: list/get/update(status-only) - no create (orders originate from
# checkout, not workflow-authorship - see the Phase 6 plan).
TEMPLATES.extend(
    [
        {
            "key": "list_orders",
            "label": "List Orders",
            "description": "Lists orders for this business, filtered (status, customer, date range) and capped.",
            "category": "Ecommerce",
            "base_node_type": "module.list",
            "icon": "shopping-cart",
            "default_config": {"module": "orders", "limit": 20},
        },
        {
            "key": "get_order",
            "label": "Get Order",
            "description": "Fetches a single order by id.",
            "category": "Ecommerce",
            "base_node_type": "module.get",
            "icon": "shopping-cart",
            "default_config": {"module": "orders"},
        },
        {
            "key": "update_order_status",
            "label": "Update Order Status",
            "description": "Updates an order's status only - no other order field can be changed from a workflow.",
            "category": "Ecommerce",
            "base_node_type": "module.update",
            "icon": "shopping-cart",
            "default_config": {"module": "orders", "fields": {"status": "paid"}},
        },
    ]
)

# Payments: list/get only - no create/update (a payment record must only
# ever be created by the real provider webhook - see the Phase 6 plan).
TEMPLATES.extend(
    [
        {
            "key": "list_payments",
            "label": "List Payments",
            "description": "Lists payments for this business, filtered (status, order, customer) and capped.",
            "category": "Ecommerce",
            "base_node_type": "module.list",
            "icon": "credit-card",
            "default_config": {"module": "payments", "limit": 20},
        },
        {
            "key": "get_payment",
            "label": "Get Payment",
            "description": "Fetches a single payment by id.",
            "category": "Ecommerce",
            "base_node_type": "module.get",
            "icon": "credit-card",
            "default_config": {"module": "payments"},
        },
    ]
)

for _t in TEMPLATES:
    _t.setdefault("config_schema_overrides", None)
    _t.setdefault("is_active", True)
    # Phase 7 Part A: gate each generic-executor template on the same
    # module it queries - identical to its own default_config["module"].
    _t.setdefault("required_connector_type_key", _t["default_config"]["module"])


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
