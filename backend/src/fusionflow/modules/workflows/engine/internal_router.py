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
- Post-visit feedback asks becoming due a day after an appointment
  (`feedback_poller.py`) - a once-daily cadence is plenty for this one's
  "was this yesterday" check.
- Appointment reminders due ~2 hours before a confirmed slot
  (`appointment_reminder_poller.py`) - unlike the daily-granularity check
  above, this one genuinely needs a tighter cadence than once a day to
  land anywhere near "2 hours before" a specific time.

Two schedulers hit this route, not one, because Vercel's Hobby plan
caps its own Cron Jobs feature at once a day (a tighter schedule gets the
*entire deployment* rejected at build time - the cause of a real incident
where backend deploys silently stopped picking up new commits for a long
stretch): `backend/vercel.json`'s cron fires once daily as a baseline
safety net, and `.github/workflows/scheduled-tasks-cron.yml` fires every
15 minutes via GitHub Actions (not subject to Vercel's limit at all,
since it's an ordinary external HTTP caller) to give
`appointment_reminder_poller`/`flow.delay`/`schedule_poller` the tight
cadence they actually need. Both send `Authorization: Bearer
<CRON_SECRET>` - `_verify_cron_secret` below checks that header against
`Settings.CRON_SECRET` regardless of which scheduler called it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Header, HTTPException

from fusionflow.config import get_settings
from fusionflow.modules.workflows.engine import (
    appointment_reminder_poller,
    feedback_poller,
    outbox_poller,
    schedule_poller,
)

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
    feedback_asks_attempted = await feedback_poller.poll_once()
    reminders_sent = await appointment_reminder_poller.poll_once()
    return {
        "inbox_processed": inbox_processed,
        "schedules_fired": schedules_fired,
        "feedback_asks_attempted": feedback_asks_attempted,
        "reminders_sent": reminders_sent,
    }
