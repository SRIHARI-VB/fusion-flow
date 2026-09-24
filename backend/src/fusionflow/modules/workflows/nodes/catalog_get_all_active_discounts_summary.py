"""`catalog.get_all_active_discounts_summary` — the broad-listing sibling
of `catalog.get_active_discounts`: where that node answers "is there a
discount for *this one* service/product" (used once a specific treatment
is already known, e.g. after `instagram.ask_choice` or a dynamic-listing
detail view), this node answers "what's on offer *at all* right now, and
for which treatments" - for the general consultation flow, which doesn't
know which treatment the customer wants until several messages later.

Wraps `catalog.service.get_all_active_discounts_with_targets` and joins
its per-target rows into one pre-formatted text block - `resolve_path`
only ever traverses dicts, never lists, so a template can't loop over
`{{node.discounts}}` itself; this node does that join server-side, the
same reasoning every other list-flattening node in this package gives
(`record_get_latest.py`, `catalog_get_active_discounts.py`).
"""

from __future__ import annotations

from pydantic import BaseModel

from fusionflow.modules.catalog import service as catalog_service
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "has_discount": {"type": "boolean"},
        "summary": {"type": "string"},
        "discounts": {"type": "array"},
    },
}


class GetAllActiveDiscountsSummaryConfig(BaseModel):
    pass


def _format_amount(discount_type: str | None, discount_value: str | None) -> str:
    if discount_type is None or discount_value is None:
        return ""
    if discount_type == "percentage":
        return f"{discount_value}%"
    return discount_value


def _summarize(discounts: list[dict]) -> str:
    if not discounts:
        return ""
    lines = []
    for d in discounts:
        amount = _format_amount(d["discount_type"], d["discount_value"])
        if d["kind"] == "coupon":
            detail = f"use code {d['label']} for {amount} off" if amount else f"use code {d['label']}"
        else:
            detail = f"{d['label']} - {amount} off" if amount else d["label"]
        lines.append(f"• {d['target_name']}: {detail}")
    return "🎁 Current offers:\n" + "\n".join(lines)


class GetAllActiveDiscountsSummaryExecutor(NodeExecutor):
    node_type = "catalog.get_all_active_discounts_summary"
    kind = "action"
    category = "Data"
    label = "Get All Active Discounts Summary"
    description = "Lists every currently-active coupon/offer that's scoped to a specific service/product, pre-joined into one 'here's what's on offer' message block."
    config_model = GetAllActiveDiscountsSummaryConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = False

    async def execute(self, context: ExecutionContext) -> NodeResult:
        discounts = await catalog_service.get_all_active_discounts_with_targets(context.session, context.tenant_id)
        return Success(
            output={"has_discount": bool(discounts), "summary": _summarize(discounts), "discounts": discounts}
        )


node_executor_registry.register(GetAllActiveDiscountsSummaryExecutor())
