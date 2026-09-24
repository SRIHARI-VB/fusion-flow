"""`catalog.classify_consultation_bucket` — a small, Faheem-shaped bridge
between a dynamically-picked catalog service and the pre-existing,
hand-authored "what's this consultation about" concern chain
(`CONCERN_ORTHO`/`CONCERN_OTHER` postback literals, matched by that
workflow's own condition nodes).

That concern chain - ticket creation, patient-name collection, an
ask-the-doctor step, day/time selection, booking - is a long, already-
built and already-tested multi-run suspend chain. Rebuilding an
equivalent parallel chain for "a specific catalog service was already
picked" would duplicate all of it for no real benefit; re-entering the
*existing* chain by sending its own `CONCERN_ORTHO`/`CONCERN_OTHER`
literal (exactly as if the customer had tapped that button themselves)
reuses 100% of it. This node's only job is picking *which* literal to
send, from the picked service's name - a keyword heuristic, not a
platform-generic concept, so this is deliberately not a `records.*`/
`module.*` node: a tenant with different concern categories, or none at
all, has no reason to reuse it.
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

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "bucket": {"type": "string"},
        "concern_payload": {"type": "string"},
    },
}

# Faheem's own two concern buckets - CONCERN_EMERGENCY is a third, separate
# path (already handled by its own dedicated emergency-slot flow, not this
# node's concern), so it's deliberately not a possible output here.
_ORTHO_KEYWORDS = ("brace", "align", "ortho")


class ClassifyConsultationBucketConfig(BaseModel):
    name: str = Field(min_length=1, description="The picked service's name, usually '{{...item.name}}'.")


class ClassifyConsultationBucketExecutor(NodeExecutor):
    node_type = "catalog.classify_consultation_bucket"
    kind = "action"
    category = "Data"
    label = "Classify Consultation Bucket"
    description = "Maps a service name to this workflow's CONCERN_ORTHO/CONCERN_OTHER postback literal, by keyword."
    config_model = ClassifyConsultationBucketConfig
    output_schema = _OUTPUT_SCHEMA
    retryable = False

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = ClassifyConsultationBucketConfig.model_validate(context.config)
        name = interpolate(config.name, context.variables).lower()

        if any(keyword in name for keyword in _ORTHO_KEYWORDS):
            return Success(output={"bucket": "ortho", "concern_payload": "CONCERN_ORTHO"})
        return Success(output={"bucket": "other", "concern_payload": "CONCERN_OTHER"})


node_executor_registry.register(ClassifyConsultationBucketExecutor())
