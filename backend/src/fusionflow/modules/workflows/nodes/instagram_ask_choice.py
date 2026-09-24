"""`instagram.ask_choice` — sends a text prompt with a Meta "button
template" message (up to 3 tappable postback buttons), whose options come
live from any module - a fixed one (Products, Services, ...) or a tenant's
own custom object type (`business_objects`) - via `source.kind == "module"`.
Mirrors `whatsapp.ask_choice`'s `ModuleSource` mechanism (see that node's
own module docstring for the `_get_field` dotted-path rationale), but NOT
its suspend/resume mechanic.

Critical architecture difference from WhatsApp: in this codebase's
Instagram flow a button tap does not resume a suspended node - Meta's
Messaging webhook always starts a brand-new `WorkflowRun` (a fresh
postback-triggered run keyed on `trigger.postback.payload`, see
`instagram_postback_received.py`), matched downstream by a separate
`condition.field_compare`/`condition.multi_branch` node against known
literal payload strings, in an entirely separate run wired via graph
edges/triggers - not by this node's own execution. So this node never
suspends: it just sends the message with buttons and completes, exactly
like `connector.action` already does for the `send_button_template`
action (see `connector_action.py`) - it has no `extract_resume_value` and
never returns `Suspend`.

Meta hard-caps a single button template at 3 buttons (`send_button_template`'s
own docstring in `modules/connectors/instagram/adapter.py`) and a button
title at 20 characters (the same limit `_whatsapp_common.py::ButtonEntry`
already documents for WhatsApp's own quick-reply buttons - Meta enforces
the same title cap across both button-template surfaces). Showing more
than 3 options is a known, already-solved *graph-authoring* pattern in
this codebase's live Faheem workflow: chain multiple `instagram.ask_choice`
instances back-to-back ("page 1" / "page 2"), each with its own `limit`/
`offset` into the same module+filters - not something a single node
instance does internally. `offset` exists on this node's config for
exactly that chaining.

The actual point of this node beyond being an Instagram port of
`whatsapp.ask_choice`: a Services/Products option whose id has an active
coupon or offer (`catalog.service.get_active_discounts`) gets its button
title annotated with a trailing " 🎁" (truncating the base label first so
the annotated title still respects Meta's 20-character cap) - so a
customer picking from a live services/products list sees at a glance
which options currently have a discount, without a separate node.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.base import registry as connector_registry
from fusionflow.modules.workflows.engine.module_registry import interpolate_dict_values, resolve_adapter
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate

# Meta's own button-template limits (see `send_button_template`'s docstring
# in `modules/connectors/instagram/adapter.py`, and `_whatsapp_common.py`'s
# `ButtonEntry.title`'s identical 20-char cap for the sibling WhatsApp
# surface).
_MAX_BUTTONS = 3
_MAX_TITLE_LENGTH = 20
_DISCOUNT_SUFFIX = " \U0001f381"  # " 🎁"


class ModuleSource(BaseModel):
    kind: Literal["module"] = "module"
    module: str = Field(min_length=1, description="A module key from GET /workflows/modules - fixed or custom.")
    filters: dict[str, Any] = Field(default_factory=dict)
    label_field: str = Field(default="name")
    value_field: str = Field(default="id")
    limit: int = Field(default=3, ge=1, le=_MAX_BUTTONS, description="Meta's own 3-button-per-message cap.")
    offset: int = Field(
        default=0,
        ge=0,
        description="Skip this many matching rows before taking `limit` - chain two instances of this "
        "node (offset=0/limit=3, then offset=3/limit=3, ...) to page through more than 3 options, "
        "matching this codebase's existing hardcoded 'page 1'/'page 2' treatment-picker pattern.",
    )


class AskChoiceConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    recipient_id: str = Field(
        min_length=1,
        description="The customer's Instagram-scoped sender id (usually {{trigger.sender_id}}).",
        json_schema_extra={"format": "recipient"},
    )
    text: str = Field(min_length=1, json_schema_extra={"format": "textarea"})
    source: ModuleSource


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "sent_count": {"type": "integer"},
        "has_more": {"type": "boolean"},
    },
}


def _get_field(row: dict[str, Any], path: str) -> Any:
    """Resolves `label_field`/`value_field` against a module row - a plain
    key for a fixed module's flat `*Out` dict (e.g. `"name"`), or a dotted
    path for a custom object type's nested `ObjectRecordOut.payload`
    (e.g. `"payload.preferred_time"`). Copied from `whatsapp_ask_choice.py`
    rather than shared, matching that node's own "purely additive" framing -
    a one-off helper, not worth a cross-module import for."""
    current: Any = row
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


async def _resolve_instagram_instance(context: ExecutionContext, connector_instance_id_str: str):
    """Same `connector_instance_id` -> `ConnectorInstance` resolution
    `connector_action.py` does inline - there is no shared Instagram
    equivalent of `_whatsapp_common.py::resolve_whatsapp_instance` yet, and
    adding one for a single call site here isn't worth it."""
    try:
        connector_instance_id = uuid.UUID(connector_instance_id_str)
    except ValueError:
        return Failure(f"connector_instance_id {connector_instance_id_str!r} is not a valid UUID")

    instance = await connector_service.get_instance(
        context.session, tenant_id=context.tenant_id, instance_id=connector_instance_id
    )
    if instance is None:
        return Failure(f"connector instance {connector_instance_id} not found for this tenant")
    return instance


async def _discount_suffix_for(context: ExecutionContext, module: str, value_field_raw: Any) -> str:
    """Returns `_DISCOUNT_SUFFIX` if `catalog.service.get_active_discounts`
    finds any active coupon/offer scoped to this row's id, else `""`. Only
    ever called for `module in ("services", "products")` with a
    UUID-parseable id - any other module, or a non-UUID id (a custom
    object type's own row ids aren't necessarily UUIDs), skips the lookup
    entirely rather than raising, matching this codebase's "no-match-is-
    not-an-error" convention (see `record_get_latest.py`)."""
    if module not in ("services", "products"):
        return ""
    try:
        row_id = uuid.UUID(str(value_field_raw))
    except (ValueError, TypeError):
        return ""

    from fusionflow.modules.catalog import service as catalog_service

    discounts = await catalog_service.get_active_discounts(
        context.session,
        context.tenant_id,
        service_id=row_id if module == "services" else None,
        product_id=row_id if module == "products" else None,
    )
    return _DISCOUNT_SUFFIX if discounts else ""


class AskChoiceExecutor(NodeExecutor):
    node_type = "instagram.ask_choice"
    kind = "action"
    category = "Messages"
    subcategory = "Ask"
    palette_group = "Talk to Customer"
    icon = "list-checks"
    label = "Ask Customer to Choose (Instagram)"
    description = (
        "Sends a text prompt with up to 3 tappable buttons pulled live from a module (e.g. Services), "
        "annotating any option with an active discount. Does not wait for a reply - a tap starts a "
        "new run, matched downstream by a condition node on the postback payload."
    )
    config_model = AskChoiceConfig
    output_schema = _OUTPUT_SCHEMA
    # See this module's own docstring: a button tap never resumes this
    # node - it always starts a fresh postback-triggered run - so unlike
    # `whatsapp.ask_choice` this is a plain, non-suspending action, exactly
    # like `connector.action`'s own `send_button_template` dispatch.
    required_connector_type_key = "instagram"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = AskChoiceConfig.model_validate(context.config)
        recipient_id = interpolate(config.recipient_id, context.variables)
        text = interpolate(config.text, context.variables)

        instance = await _resolve_instagram_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        adapter = connector_registry.get_or_none(instance.connector_type.key)
        if adapter is None:
            return Failure(f"no adapter registered for connector instance {instance.id}")

        module_adapter = await resolve_adapter(
            context.session, tenant_id=context.tenant_id, module_key=config.source.module
        )
        if module_adapter is None:
            return Failure(f"unknown module {config.source.module!r}")

        filters = interpolate_dict_values(config.source.filters, context.variables)

        # `ModuleQueryAdapter.list` (see `engine/module_registry.py`) has no
        # `offset` param today - fetch one extra row past the requested
        # window (limit+offset+1) and slice/trim in Python, rather than
        # erroring or waiting on an engine-wide signature change. The "+1"
        # row (if present) is only ever used to compute `has_more`, never
        # sent as a button.
        try:
            rows = await module_adapter.list(
                context.session,
                tenant_id=context.tenant_id,
                filters=filters,
                limit=config.source.limit + config.source.offset + 1,
            )
        except (ValueError, LookupError) as exc:
            return Failure(str(exc))

        window = rows[config.source.offset : config.source.offset + config.source.limit]
        has_more = len(rows) > config.source.offset + config.source.limit

        if not window:
            # Nothing to show - Meta rejects an empty `buttons` array (see
            # `send_button_template`'s `perform_action` dispatch), so don't
            # even attempt the send. A workflow author branches on
            # `sent_count == 0` downstream to show a "nothing available"
            # fallback instead.
            return Success(output={"sent_count": 0, "has_more": False})

        buttons: list[dict[str, str]] = []
        for row in window:
            value = _get_field(row, config.source.value_field)
            base_title = str(_get_field(row, config.source.label_field) or "")
            suffix = await _discount_suffix_for(context, config.source.module, value)
            title = base_title[: _MAX_TITLE_LENGTH - len(suffix)] + suffix if suffix else base_title[:_MAX_TITLE_LENGTH]
            buttons.append({"type": "postback", "title": title, "payload": str(value)})

        try:
            await adapter.perform_action(
                action="send_button_template",
                params={"recipient_id": recipient_id, "text": text, "buttons": buttons},
                instance=instance,
                session=context.session,
            )
        except NotImplementedError as exc:
            return Failure(str(exc))

        return Success(output={"sent_count": len(buttons), "has_more": has_more})


node_executor_registry.register(AskChoiceExecutor())
