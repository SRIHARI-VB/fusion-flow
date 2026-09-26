"""`data.compose_text` — joins a list of optional text "parts" into one
string, silently dropping any part whose own value resolves empty
(instead of leaving a bare label or a stray separator behind).

Every other templating primitive in this engine (`interpolate`,
`data.transform`) is a straight substitution - there's no `{{if x}}`
syntax, so a message field that should either show "Note: <text>" or
show nothing at all (never a dangling "Note: " with nothing after it)
has nowhere to express that conditional. This node is the minimal
generic building block for that one recurring shape: given `parts`
(each an optional `value` + a `prefix` applied only when that value is
actually non-empty), it renders only the non-empty ones and joins them
with `joiner`.

Doubles as the fix for "don't overwrite a customer's second note with
their first" - joining `[existing_history, new_note]` with a separator
already gets the "first note ever" case right for free (the empty
`existing_history` part is dropped rather than leaving a leading
separator behind), without a second, more special-cased node.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate


class ComposeTextPart(BaseModel):
    value: str = Field(description="Templated - this part is dropped entirely if this resolves empty (after trimming).")
    prefix: str = Field(default="", description="Templated or literal - prepended only when `value` is non-empty.")


class ComposeTextConfig(BaseModel):
    parts: list[ComposeTextPart] = Field(min_length=1)
    joiner: str = Field(default="\n", description="Literal (or templated) separator placed between the non-empty rendered parts.")


_OUTPUT_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}}


class ComposeTextExecutor(NodeExecutor):
    node_type = "data.compose_text"
    kind = "action"
    category = "Data"
    label = "Compose Text (skip empty parts)"
    description = "Joins optional text parts into one string, dropping any part whose value is empty instead of leaving a bare label or stray separator."
    config_model = ComposeTextConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = False

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ComposeTextConfig.model_validate(context.config)
        joiner = interpolate(config.joiner, context.variables)

        rendered: list[str] = []
        for part in config.parts:
            value = interpolate(part.value, context.variables).strip()
            if not value:
                continue
            prefix = interpolate(part.prefix, context.variables) if part.prefix else ""
            rendered.append(f"{prefix}{value}")

        return Success(output={"text": joiner.join(rendered)})


node_executor_registry.register(ComposeTextExecutor())
