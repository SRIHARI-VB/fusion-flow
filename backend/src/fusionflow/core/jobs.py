"""Background-job abstraction — "provision but skip in dev".

The workflow engine and the outbox poller (later waves) are written only
against the `JobQueue` protocol, never against Celery APIs, so local dev
needs no broker at all. Swapping to Celery later is a
`get_job_queue()` change, not a rewrite of every call site.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fusionflow.config import Settings

logger = logging.getLogger(__name__)

JobHandler = Callable[..., Awaitable[Any]]


@runtime_checkable
class JobQueue(Protocol):
    """Minimal enqueue/dispatch surface shared by every job backend."""

    def register_handler(self, job_name: str, handler: JobHandler) -> None: ...

    async def enqueue(self, job_name: str, **kwargs: Any) -> None: ...


class InProcessAsyncQueue:
    """asyncio-task based job queue. The dev/phase-1 default.

    `enqueue` schedules the handler with `asyncio.create_task` and retries
    a bounded number of times with a fixed backoff. This is intentionally
    in-memory and best-effort: jobs are lost on process restart, which is
    acceptable in phase 1 because durable work is driven off the
    transactional outbox table (a crashed job's inbox row is simply picked
    up again by the poller), not off this queue's memory.
    """

    def __init__(self, max_retries: int = 3, retry_delay_seconds: float = 1.0) -> None:
        self._handlers: dict[str, JobHandler] = {}
        self._tasks: set[asyncio.Task[Any]] = set()
        self._max_retries = max_retries
        self._retry_delay_seconds = retry_delay_seconds

    def register_handler(self, job_name: str, handler: JobHandler) -> None:
        if job_name in self._handlers:
            raise ValueError(f"job handler already registered for {job_name!r}")
        self._handlers[job_name] = handler

    async def enqueue(self, job_name: str, **kwargs: Any) -> None:
        if job_name not in self._handlers:
            raise KeyError(f"no handler registered for job {job_name!r}")
        task = asyncio.create_task(self._run_with_retries(job_name, kwargs))
        # Keep a strong reference: asyncio only holds weak refs to tasks,
        # so an un-referenced task can be garbage collected mid-flight.
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run_with_retries(self, job_name: str, kwargs: dict[str, Any]) -> None:
        handler = self._handlers[job_name]
        for attempt in range(1, self._max_retries + 1):
            try:
                await handler(**kwargs)
                return
            except asyncio.CancelledError:
                raise
            except Exception:
                if attempt >= self._max_retries:
                    logger.exception(
                        "job %s failed permanently after %d attempts", job_name, attempt
                    )
                    return
                logger.warning(
                    "job %s failed on attempt %d/%d, retrying",
                    job_name,
                    attempt,
                    self._max_retries,
                )
                await asyncio.sleep(self._retry_delay_seconds)

    async def drain(self) -> None:
        """Await all in-flight jobs. Used by tests and graceful shutdown."""
        while self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)


class CeleryQueue:
    """Placeholder for the Celery-backed queue. Not wired yet.

    Exists so the swap point is visible in the codebase and so nothing is
    tempted to import Celery directly elsewhere. `celery` is an optional
    extra and is deliberately never imported here.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        raise NotImplementedError(
            "Celery integration not yet wired — set BACKGROUND_JOBS_ENABLED=false"
        )

    def register_handler(self, job_name: str, handler: JobHandler) -> None:  # pragma: no cover
        raise NotImplementedError

    async def enqueue(self, job_name: str, **kwargs: Any) -> None:  # pragma: no cover
        raise NotImplementedError


def get_job_queue(settings: Settings) -> JobQueue:
    """Select the job backend once, at startup, from configuration."""
    if settings.BACKGROUND_JOBS_ENABLED:
        return CeleryQueue()
    return InProcessAsyncQueue()
