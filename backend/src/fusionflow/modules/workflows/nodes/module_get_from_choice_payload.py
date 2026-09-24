"""`module.get_from_choice_payload` — the safe consumer half of
`instagram.ask_choice`'s dynamically-generated `"<module>:<id>"` postback
payloads.

A postback-triggered run has no other way to know a tapped button came
from a module-sourced choice, or which module it was - unlike
`module.get`, which treats "not found" as a hard `Failure` (correct for a
workflow author who *knows* the id should exist), this node treats
"payload isn't a well-formed `module:id` pair", "module unknown", "id
isn't UUID-shaped", and "id not found" all as the same ordinary negative:
`{"found": False, "module": None, "item": None}`. That makes it safe to
wire as a postback-routing chain's final fallback - reached by *any*
unmatched postback, not just ones this node's own producer generated -
without risking `ChildExecutionError`/`RunStatus.FAILED` on a stale/replay/
garbage tap, the same "no-match-is-not-an-error" convention
`record_get_latest.py` and `records.get_latest` already establish.
"""

from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.module_registry import resolve_adapter
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
        "found": {"type": "boolean"},
        "module": {"type": ["string", "null"]},
        "item": {"type": ["object", "null"]},
    },
}

_NOT_FOUND: dict[str, Any] = {"found": False, "module": None, "item": None}


class GetFromChoicePayloadConfig(BaseModel):
    payload: str = Field(
        min_length=1,
        description="The raw postback payload to parse, usually '{{trigger.payload}}'.",
    )


class GetFromChoicePayloadExecutor(NodeExecutor):
    node_type = "module.get_from_choice_payload"
    kind = "action"
    category = "Data"
    label = "Get Record From Choice Payload"
    description = (
        "Parses an instagram.ask_choice-style '<module>:<id>' postback payload and fetches that row - "
        "resolves to 'not found' instead of failing the run for anything malformed or missing, so it's "
        "safe to use as a postback chain's catch-all fallback."
    )
    config_model = GetFromChoicePayloadConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = False

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = GetFromChoicePayloadConfig.model_validate(context.config)
        raw = interpolate(config.payload, context.variables)

        if not isinstance(raw, str) or ":" not in raw:
            return Success(output=dict(_NOT_FOUND))

        module_key, _, id_part = raw.partition(":")
        if not module_key or not id_part:
            return Success(output=dict(_NOT_FOUND))

        try:
            item_id = uuid.UUID(id_part)
        except ValueError:
            return Success(output=dict(_NOT_FOUND))

        adapter = await resolve_adapter(context.session, tenant_id=context.tenant_id, module_key=module_key)
        if adapter is None:
            return Success(output=dict(_NOT_FOUND))

        item = await adapter.get(context.session, tenant_id=context.tenant_id, item_id=item_id)
        if item is None:
            return Success(output=dict(_NOT_FOUND))

        return Success(output={"found": True, "module": module_key, "item": item})


node_executor_registry.register(GetFromChoicePayloadExecutor())
