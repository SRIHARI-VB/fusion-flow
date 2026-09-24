"""`catalog.get_active_discounts` — a plain workflow-node wrapper around
`catalog.service.get_active_discounts`, so a message can mention an active
coupon/offer without a workflow author needing `records.query` plus
manual date-window filtering (that function already does both). Produces
a pre-joined `summary` string too - `resolve_path` only ever traverses
dicts, never lists, so a template like `{{node.discounts.0.label}}` could
never resolve; this node does the "first (or only) human-readable line"
join itself, the same reasoning `record_get_latest.py` gives for
flattening a list into one object.

`service_id`/`product_id` are both optional, but at least one must
resolve to a real id to get any results - `catalog.service.
get_active_discounts`'s own `_applies_to_target` check returns `False`
whenever both are `None` (an empty/unscoped `applies_to` never matches
"no id given" - it's not a tenant-wide wildcard), so calling this node
with neither templated to a real id always yields `has_discount: False`.
This node does not attempt a tenant-wide "any active promotion" lookup;
scope it to one real service/product id.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from fusionflow.modules.catalog import service as catalog_service
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "has_discount": {"type": "boolean"},
        "summary": {"type": "string"},
        "discounts": {"type": "array"},
    },
}


class GetActiveDiscountsConfig(BaseModel):
    service_id: str = Field(default="", description="Templated service id, e.g. '{{resolve-choice.item.id}}'.")
    product_id: str = Field(default="", description="Templated product id.")


def _summarize(discounts: list[dict]) -> str:
    if not discounts:
        return ""
    parts = []
    for d in discounts:
        amount = _format_amount(d["discount_type"], d["discount_value"])
        if d["kind"] == "coupon":
            parts.append(f"use code {d['label']} for {amount} off" if amount else f"use code {d['label']} for a discount")
        else:
            parts.append(f"{d['label']} - {amount} off" if amount else d["label"])
    return "🎁 " + "; ".join(parts)


def _format_amount(discount_type: str | None, discount_value: str | None) -> str:
    """Mirrors the frontend's own percentage-vs-flat-amount display
    convention (see CouponsPage.tsx's table cell: `discount_type ===
    "percentage" ? value + "%" : value`) - no currency symbol, matching
    that established convention exactly."""
    if discount_type is None or discount_value is None:
        return ""
    if discount_type == "percentage":
        return f"{discount_value}%"
    return discount_value


class GetActiveDiscountsExecutor(NodeExecutor):
    node_type = "catalog.get_active_discounts"
    kind = "action"
    category = "Data"
    label = "Get Active Discounts"
    description = "Looks up any active coupon/offer scoped to a service/product (or tenant-wide), pre-joined into one summary line."
    config_model = GetActiveDiscountsConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = False

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = GetActiveDiscountsConfig.model_validate(context.config)

        def _parse(raw: str) -> uuid.UUID | None:
            resolved = interpolate(raw, context.variables).strip() if raw else ""
            if not resolved:
                return None
            try:
                return uuid.UUID(resolved)
            except ValueError:
                return None

        discounts = await catalog_service.get_active_discounts(
            context.session,
            context.tenant_id,
            service_id=_parse(config.service_id),
            product_id=_parse(config.product_id),
        )
        return Success(
            output={"has_discount": bool(discounts), "summary": _summarize(discounts), "discounts": discounts}
        )


node_executor_registry.register(GetActiveDiscountsExecutor())
