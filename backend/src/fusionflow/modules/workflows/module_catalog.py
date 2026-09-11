"""Unified module-picker catalog for the composable-workflow-builder
redesign (Phase 3): one merged list of every "kind of record" a workflow
author can point `records.query`/`records.upsert` (and, later, a module-
sourced `whatsapp.ask_choice`) at — the 9 fixed modules already reachable
through `module.list`/`module.get`/`module.create`/`module.update`, and
every one of this tenant's own custom object types (`business_objects`).

`FIXED_MODULE_CATALOG`'s label/icon/category values are the single source
of truth `scripts/seed_module_query_templates.py`'s friendly CRUD templates
now build from too (see that script) — so the two can never drift the way
they would if each kept its own hand-maintained copy. `supported_operations`
is deliberately NOT stored here as a static field: it's computed fresh by
introspecting each fixed module's real, registered `ModuleQueryAdapter`
(which of `list`/`get`/`create`/`update` it actually overrides) so this
catalog can never claim a capability (e.g. "Orders supports create") the
adapter itself doesn't have.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any, Sequence

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.business_objects import service as business_objects_service
from fusionflow.modules.business_objects.models import ObjectFieldDefinition
from fusionflow.modules.catalog.schemas import CouponCreate, OfferCreate, ProductServiceCreate
from fusionflow.modules.customers.schemas import CustomerCreate
from fusionflow.modules.custom_fields import service as custom_fields_service
from fusionflow.modules.custom_fields.models import EntityType, FieldDefinition
from fusionflow.modules.kb.schemas import KbArticleCreate
from fusionflow.modules.tickets.schemas import TicketCreate
from fusionflow.modules.workflows.engine.module_registry import ModuleQueryAdapter
from fusionflow.modules.workflows.engine.module_registry import registry as module_registry
from fusionflow.modules.workflows.nodes import _module_adapters  # noqa: F401 - side-effect import


@dataclasses.dataclass(frozen=True)
class ModuleCatalogSpec:
    """Display metadata for one fixed module."""

    module_key: str
    label: str
    category: str
    icon: str
    create_schema: type[BaseModel] | None = None
    custom_fields_entity_type: EntityType | None = None
    create_schema_exclude: frozenset[str] = dataclasses.field(default_factory=lambda: frozenset({"custom_fields"}))


#: Every fixed module reachable through `module.*`/`records.*`. Orders and
#: payments have no `create_schema` — neither adapter supports `create`
#: (payments never; orders only via the real checkout path, not a
#: workflow), so there is no "fields for creating one" to show a workflow
#: author in the first place.
FIXED_MODULE_CATALOG: dict[str, ModuleCatalogSpec] = {
    "products": ModuleCatalogSpec(
        "products", "Product", "Ecommerce", "package", ProductServiceCreate, EntityType.PRODUCT,
        frozenset({"custom_fields", "entity_type"}),
    ),
    "services": ModuleCatalogSpec(
        "services", "Service", "Ecommerce", "wrench", ProductServiceCreate, EntityType.SERVICE,
        frozenset({"custom_fields", "entity_type"}),
    ),
    "coupons": ModuleCatalogSpec("coupons", "Coupon", "Ecommerce", "ticket-percent", CouponCreate, EntityType.COUPON),
    "offers": ModuleCatalogSpec("offers", "Offer", "Ecommerce", "gift", OfferCreate, EntityType.OFFER),
    "customers": ModuleCatalogSpec("customers", "Customer", "Customers", "users", CustomerCreate),
    "tickets": ModuleCatalogSpec("tickets", "Ticket", "Support", "life-buoy", TicketCreate),
    "kb": ModuleCatalogSpec("kb", "KB Article", "Data", "book-open", KbArticleCreate),
    "orders": ModuleCatalogSpec("orders", "Order", "Ecommerce", "shopping-cart"),
    "payments": ModuleCatalogSpec("payments", "Payment", "Ecommerce", "credit-card"),
}


def supported_operations(module_key: str) -> list[str]:
    """Which of list/get/create/update `module_key`'s real, registered
    adapter actually overrides — the adapter class is the source of truth
    for what's callable, not a second hand-maintained list here."""
    adapter = module_registry.get_or_none(module_key)
    if adapter is None:
        return []
    return [
        op
        for op in ("list", "get", "create", "update")
        if getattr(type(adapter), op) is not getattr(ModuleQueryAdapter, op)
    ]


def _resolve_prop(prop: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Follows one level of Pydantic v2's `$ref`/`anyOf`-wrapped-optional
    JSON-schema shapes so `_field_type_for` sees the real `type`/`enum`
    instead of an indirection wrapper. Good enough for this codebase's
    actual schemas (flat models, no deeply nested unions) - not a general
    JSON-Schema resolver."""
    ref = prop.get("$ref")
    if ref:
        return {**defs.get(ref.rsplit("/", 1)[-1], {}), **{k: v for k, v in prop.items() if k != "$ref"}}
    for union_key in ("anyOf", "oneOf"):
        options = prop.get(union_key)
        if options:
            for option in options:
                if option.get("type") != "null":
                    return _resolve_prop(option, defs)
    return prop


def _field_type_for(resolved: dict[str, Any]) -> str:
    if "enum" in resolved:
        return "select"
    json_type = resolved.get("type")
    if json_type in ("integer", "number"):
        return "number"
    if json_type == "boolean":
        return "boolean"
    if json_type == "array":
        return "multiselect"
    if resolved.get("format") in ("date", "date-time"):
        return "date"
    return "text"


def _schema_to_fields(schema_cls: type[BaseModel] | None, *, exclude: frozenset[str]) -> list[dict[str, Any]]:
    """Turns a `*Create` Pydantic schema's JSON schema into the same flat
    `{key, label, field_type, options, required}` shape a tenant's own
    `FieldDefinition`/`ObjectFieldDefinition` rows already have — one shape
    for the frontend's future module-aware field form to render, whether a
    field comes from a fixed schema or a tenant's own definition."""
    if schema_cls is None:
        return []
    schema = schema_cls.model_json_schema()
    defs = schema.get("$defs", {})
    required = set(schema.get("required", []))
    fields: list[dict[str, Any]] = []
    for key, prop in schema.get("properties", {}).items():
        if key in exclude:
            continue
        resolved = _resolve_prop(prop, defs)
        fields.append(
            {
                "key": key,
                "label": resolved.get("title") or key.replace("_", " ").title(),
                "field_type": _field_type_for(resolved),
                "options": resolved.get("enum"),
                "required": key in required,
            }
        )
    return fields


def _field_def_to_dict(field_def: FieldDefinition | ObjectFieldDefinition) -> dict[str, Any]:
    field_type = field_def.field_type
    return {
        "key": field_def.key,
        "label": field_def.label,
        "field_type": field_type.value if hasattr(field_type, "value") else str(field_type),
        "options": field_def.options,
        "required": field_def.required,
    }


@dataclasses.dataclass(frozen=True)
class ModuleCatalogEntry:
    """Plain-data return shape `service.py`/`router.py` converts to
    `schemas.ModuleCatalogEntryOut` — kept dependency-free of `schemas.py`
    here to avoid this module importing back into `workflows.schemas` (which
    has no reason to import `module_catalog` itself, but keeping the
    direction one-way avoids ever having to worry about it)."""

    key: str
    label: str
    icon: str | None
    category: str
    source: str
    supported_operations: list[str]
    fields: list[dict[str, Any]]


async def list_modules(session: AsyncSession, *, tenant_id: uuid.UUID) -> list["ModuleCatalogEntry"]:
    """Merges the fixed modules and this tenant's own custom object types
    into one list - see the module docstring for why each half is built
    the way it is."""
    entries: list[ModuleCatalogEntry] = []

    for spec in FIXED_MODULE_CATALOG.values():
        fields = _schema_to_fields(spec.create_schema, exclude=spec.create_schema_exclude)
        if spec.custom_fields_entity_type is not None:
            tenant_field_defs: Sequence[FieldDefinition] = await custom_fields_service.list_field_definitions(
                session, tenant_id=tenant_id, entity_type=spec.custom_fields_entity_type
            )
            fields.extend(_field_def_to_dict(fd) for fd in tenant_field_defs)
        entries.append(
            ModuleCatalogEntry(
                key=spec.module_key,
                label=spec.label,
                icon=spec.icon,
                category=spec.category,
                source="fixed",
                supported_operations=supported_operations(spec.module_key),
                fields=fields,
            )
        )

    object_types = await business_objects_service.list_object_types(session, tenant_id=tenant_id, is_active=True)
    for object_type in object_types:
        object_field_defs = await business_objects_service.list_field_definitions(
            session, tenant_id=tenant_id, object_type_id=object_type.id
        )
        entries.append(
            ModuleCatalogEntry(
                key=object_type.key,
                label=object_type.name,
                icon=object_type.icon,
                category="Custom",
                source="custom",
                supported_operations=["list", "get", "create", "update"],
                fields=[_field_def_to_dict(fd) for fd in object_field_defs],
            )
        )

    return entries
