"""`flow.delay` — "Reply Delay": pause a run for a fixed number of minutes
before continuing, e.g. an Instagram comment automation that waits a
couple of minutes before replying so it doesn't look instantly automated.

Uses the exact same suspend/resume machinery `whatsapp_ask_question.py`
uses to pause for a customer's reply (`Suspend` -> `WorkflowRun.status =
WAITING` -> resumed later) - the only difference is WHAT resumes it and
WHY the expiry exists:

- A reply-wait resumes when a matching inbound message arrives
  (`event_bus.find_pending_wait`), and its 24h expiry is a "give up,
  force-fail" deadline for a customer who never replies.
- A `flow.delay` wait resumes automatically once `config.minutes` has
  elapsed - nothing external correlates to it - and its expiry is the
  actual point of the node, not a failure deadline. `run_loop.py::
  _persist_suspension` and `engine/outbox_poller.py`'s sweep both
  special-case this using the sentinel `run_loop.DELAY_CORRELATION_KEY`
  every `flow.delay` suspension uses, so a delay wait is resumed
  (`resume_run`), never force-failed, once its shorter expiry passes.

Serverless note: unlike a webhook-triggered trigger dispatch (which now
runs inline within the request that caused it - see `webhooks.py::
_dispatch`), nothing inbound happens when a delay simply elapses. Its
resume genuinely depends on a periodic sweep - see `api.py`'s
`/internal/scheduled-tasks` endpoint and this deployment's Vercel Cron
Job, which is the only thing that can resume a delay wait when this app
runs serverless. A `flow.delay` node used in a deployment with neither a
real background process nor that cron configured will simply never
resume - this is a real, load-bearing operational requirement, not a
nice-to-have.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    NodeExecutor,
    NodeResult,
    Suspend,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.run_loop import DELAY_CORRELATION_KEY


class FlowDelayConfig(BaseModel):
    minutes: int = Field(ge=1, le=1440, description="How many minutes to wait before continuing (max 24h).")


class FlowDelayExecutor(NodeExecutor):
    node_type = "flow.delay"
    kind = "action"
    category = "Flow Control"
    label = "Wait"
    description = "Pauses the automation for a fixed number of minutes before continuing."
    config_model = FlowDelayConfig
    can_suspend = True

    async def execute(self, context: ExecutionContext) -> NodeResult:
        return Suspend(correlation_key=DELAY_CORRELATION_KEY)

    async def extract_resume_value(self, config: dict[str, Any], resume_payload: dict[str, Any]) -> Any:
        # Nothing external to extract - the sweep that resumes this wait
        # (`outbox_poller.py::_resume_due_delays`) passes an empty
        # `reply_payload`; this node's only "answer" is that time passed.
        return None


node_executor_registry.register(FlowDelayExecutor())
