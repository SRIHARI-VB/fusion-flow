"""`whatsapp.ask_choice` — sends a question with a set of selectable
options (as WhatsApp quick-reply buttons for <=3 options, or a tap-to-open
list for up to 10) and pauses the run until the customer answers, exactly
like `whatsapp.ask_question` — but where that node needs a hand-typed
`buttons`/`sections` list, this node's options can come either straight
from its own config (`source.kind == "static"`) or live from any module —
a fixed one (Products, Services, ...) or a tenant's own custom object type
(`business_objects`) — via `source.kind == "module"`.

Branching on the answer (e.g. "if they picked pizza, go here; if burger,
go there") is NOT something this node does itself — see
`engine/composite_branching.py` and
`engine/template_resolution.py::resolve_composite_branches`'s docstring
for why a suspending node can never branch on its own answer, and how a
*static* source gets a `condition.multi_branch` node compiled in
automatically immediately downstream, wired to this node's own per-option
output handles (rendered on the canvas from this node's own
`source.options`, not a static class attribute — see the frontend's
`deriveOutputHandles`, Phase 5). A *module*-sourced choice has no
compile-time-knowable option set (the concrete rows only exist at run
time), so it never gets this treatment — it behaves as a plain
single-successor suspending action, exactly like `whatsapp.ask_question`;
an author who needs the *record* behind the picked id (not just its id and
label) chains a `records.query` node afterward (`operation="get"`,
`item_id="{{this_node.reply.id}}"`) — one more visible, removable node,
matching this redesign's "freely add/remove building blocks" goal rather
than hiding a second query inside this one.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
from fusionflow.modules.workflows.engine.composite_branching import register_composite_branch_source
from fusionflow.modules.workflows.engine.module_registry import interpolate_dict_values, resolve_adapter
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Suspend,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate
from fusionflow.modules.workflows.nodes._whatsapp_common import resolve_whatsapp_instance


class StaticOption(BaseModel):
    id: str = Field(min_length=1, description="Echoed back in the reply when the customer picks this option.")
    label: str = Field(min_length=1, max_length=24, description="Meta's own button/list-row title limit.")


class StaticSource(BaseModel):
    kind: Literal["static"] = "static"
    options: list[StaticOption] = Field(min_length=1, max_length=10)


class ModuleSource(BaseModel):
    kind: Literal["module"] = "module"
    module: str = Field(min_length=1, description="A module key from GET /workflows/modules - fixed or custom.")
    filters: dict[str, Any] = Field(default_factory=dict)
    label_field: str = Field(default="name")
    value_field: str = Field(default="id")
    limit: int = Field(default=10, ge=1, le=10, description="Meta's own 10-row list cap.")


class AskChoiceConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(
        min_length=1,
        description="The customer's WhatsApp number to send the question to (usually {{trigger.from}}).",
        json_schema_extra={"format": "recipient"},
    )
    question: str = Field(min_length=1, json_schema_extra={"format": "textarea"})
    source: StaticSource | ModuleSource = Field(discriminator="kind")


_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "label": {"type": "string"}},
        }
    },
}


def _get_field(row: dict[str, Any], path: str) -> Any:
    """Resolves `label_field`/`value_field` against a module row - a plain
    key for a fixed module's flat `*Out` dict (e.g. `"name"`), or a dotted
    path for a custom object type's nested `ObjectRecordOut.payload`
    (e.g. `"payload.preferred_time"` - `business_objects.schemas.
    ObjectRecordOut` keeps a record's own fields under `payload`, not at
    the row's top level, unlike every fixed module's `*Out` schema). A
    single-segment path (every existing template's usage) behaves exactly
    like the plain `row.get(path)` this replaces - purely additive."""
    current: Any = row
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


class AskChoiceExecutor(NodeExecutor):
    node_type = "whatsapp.ask_choice"
    kind = "action"
    category = "Messages"
    subcategory = "Ask"
    palette_group = "Talk to Customer"
    icon = "list-checks"
    label = "Ask Customer to Choose"
    description = (
        "Shows the customer a set of options (typed in, or pulled live from a module like Products) "
        "and pauses until they pick one."
    )
    config_model = AskChoiceConfig
    output_schema = _OUTPUT_SCHEMA
    can_suspend = True
    # See whatsapp_ask_question.py's applicable_purposes comment - pausing
    # for one reply can't work inside a broadcast's flow.loop fan-out.
    applicable_purposes = ["automation"]
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = AskChoiceConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)
        question = interpolate(config.question, context.variables)

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        if isinstance(config.source, StaticSource):
            options = [{"id": opt.id, "label": opt.label} for opt in config.source.options]
        else:
            adapter = await resolve_adapter(
                context.session, tenant_id=context.tenant_id, module_key=config.source.module
            )
            if adapter is None:
                return Failure(f"unknown module {config.source.module!r}")
            filters = interpolate_dict_values(config.source.filters, context.variables)
            rows = await adapter.list(
                context.session, tenant_id=context.tenant_id, filters=filters, limit=config.source.limit
            )
            options = [
                {
                    "id": str(_get_field(row, config.source.value_field)),
                    "label": str(_get_field(row, config.source.label_field) or "")[:24],
                }
                for row in rows
            ]
            if not options:
                return Failure(f"module {config.source.module!r} returned no rows to choose from")

        if len(options) <= 3:
            await whatsapp_adapter.send_interactive_message(
                instance=instance,
                to=to,
                body_text=question,
                interactive_type="button",
                buttons=[{"id": opt["id"], "title": opt["label"]} for opt in options],
                session=context.session,
            )
        else:
            await whatsapp_adapter.send_interactive_message(
                instance=instance,
                to=to,
                body_text=question,
                interactive_type="list",
                sections=[
                    {
                        "title": question[:24],
                        "rows": [
                            {"id": opt["id"], "title": opt["label"], "description": None} for opt in options
                        ],
                    }
                ],
                session=context.session,
            )

        return Suspend(correlation_key=to)

    async def extract_resume_value(self, config: dict[str, Any], resume_payload: dict[str, Any]) -> Any:
        # `interactive.id`/`.title` are both already present on the inbound
        # webhook payload (`WhatsAppAdapter._extract_inbound_message`) - no
        # re-fetch from the module is possible or needed here (this method
        # only ever receives `config`/`resume_payload`, never a session -
        # see `NodeExecutor.extract_resume_value`'s signature). `id` is
        # `None` when the customer replied with free text instead of
        # tapping - a valid outcome the synthesized branch node's optional
        # "default" handle absorbs (see `condition_multi_branch.py`).
        interactive = resume_payload.get("interactive") or {}
        return {"id": interactive.get("id"), "label": interactive.get("title")}


def _static_options(config: dict[str, Any]) -> list[dict[str, str]] | None:
    """Composite branch source (`engine/composite_branching.py`) - only a
    *static* source has a compile-time-knowable option set to branch on; a
    module-sourced one returns `None` (see this module's own docstring for
    why). Must never raise on malformed config - publish-time validation's
    own rules report that separately."""
    try:
        source = config.get("source") or {}
        if source.get("kind") != "static":
            return None
        options = source.get("options") or []
        return [{"id": opt["id"], "label": opt.get("label", opt["id"])} for opt in options if opt.get("id")]
    except Exception:  # noqa: BLE001 - defensive: never let a compile pass crash on bad config
        return None


register_composite_branch_source("whatsapp.ask_choice", _static_options)
node_executor_registry.register(AskChoiceExecutor())
