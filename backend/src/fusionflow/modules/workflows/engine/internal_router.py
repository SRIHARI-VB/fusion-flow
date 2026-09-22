"""`/api/v1/internal/scheduled-tasks` — the serverless substitute for the
in-process `outbox_poller`/`schedule_poller` background loops
(`main.py`'s lifespan skips both when `Settings.is_serverless`).

Two things depend on a genuine time-based trigger that no inbound webhook
can piggyback on (unlike regular trigger dispatch, which now runs inline
within the webhook request that caused it - see `connectors/webhooks.py::
_dispatch`):

- `flow.delay` waits resuming once their timer elapses
  (`outbox_poller.py::_resume_due_delays`) - nothing inbound happens when
  a delay simply elapses.
- Scheduled/recurring broadcast sends firing at their `next_run_at`
  (`schedule_poller.py`) - same story, a clock-driven event has no
  webhook to attach to.

This route runs one pass of both pollers (`outbox_poller.poll_once` also
covers ordinary inbox dispatch and the 24h stale-reply-wait sweep, both
otherwise redundant with the inline webhook dispatch but harmless to
re-run) and is meant to be hit by a Vercel Cron Job (see `backend/
vercel.json`), which sends `Authorization: Bearer <CRON_SECRET>`
automatically once configured - `_verify_cron_secret` below checks that
header against `Settings.CRON_SECRET`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException

from fusionflow.config import get_settings
from fusionflow.modules.workflows.engine import outbox_poller, schedule_poller

router = APIRouter(prefix="/internal", tags=["internal"])

logger = logging.getLogger(__name__)


def _verify_cron_secret(authorization: str | None) -> None:
    secret = get_settings().CRON_SECRET
    if secret is None:
        logger.warning(
            "[internal] /scheduled-tasks called with no CRON_SECRET configured - allowing "
            "(local-dev default); set CRON_SECRET before relying on this in production."
        )
        return
    expected = f"Bearer {secret}"
    if authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing cron secret")


@router.post("/scheduled-tasks")
async def run_scheduled_tasks(authorization: str | None = Header(default=None)) -> dict[str, int]:
    _verify_cron_secret(authorization)
    inbox_processed = await outbox_poller.poll_once()
    schedules_fired = await schedule_poller.poll_once()
    return {"inbox_processed": inbox_processed, "schedules_fired": schedules_fired}
