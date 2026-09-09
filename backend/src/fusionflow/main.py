"""FastAPI application factory.

Boot contract for this service: importing this module must never require
Postgres, Redis or Celery to be reachable or even installed. The DB engine
is created lazily, the cache/job backends default to in-process
implementations, and `redis`/`celery` are imported only inside the classes
that need them.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fusionflow.api import api_router
from fusionflow.config import Settings, get_settings
from fusionflow.core.cache import get_cache_backend
from fusionflow.core.jobs import get_job_queue
from fusionflow.modules.admin.router import router as admin_router
from fusionflow.modules.workflows.engine.outbox_poller import (
    register_outbox_poller,
    start_outbox_poller,
)

# Imported for its side effect: registers every ORM class with the
# SQLAlchemy registry so string-based relationships resolve. Do not remove.
from fusionflow.db import models as _models  # noqa: F401

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Select the pluggable backends once, at startup.

    Both selections are cheap and offline: `InMemoryCacheBackend` and
    `InProcessAsyncQueue` construct no connections, so startup does not
    depend on any external service being up.
    """
    settings: Settings = app.state.settings
    app.state.cache = get_cache_backend(settings)
    app.state.jobs = get_job_queue(settings)
    logger.info(
        "fusion-flow starting: env=%s redis=%s background_jobs=%s ai=%s",
        settings.ENVIRONMENT,
        settings.REDIS_ENABLED,
        settings.BACKGROUND_JOBS_ENABLED,
        settings.AI_ENABLED,
    )

    # Workflow trigger dispatch (transactional outbox -> workflow_triggers
    # match -> workflow_runs). Runs on the same pluggable JobQueue as
    # everything else, so it is a no-op-safe asyncio task in dev and would
    # be a Celery/Redis Streams consumer in prod - see core/jobs.py.
    register_outbox_poller(app.state.jobs)
    await start_outbox_poller(app.state.jobs)

    yield
    close = getattr(app.state.cache, "aclose", None)
    if close is not None:
        await close()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="fusion-flow API",
        version="0.1.0",
        description=(
            "Multi-tenant B2B SaaS platform API. Tenant isolation is enforced by "
            "Postgres row-level security keyed on the `app.current_tenant_id` GUC."
        ),
        docs_url="/docs",  # Swagger UI
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Frontend dev servers: `frontend/web` (5173) and `frontend/admin` (5174).
    # allow_credentials is required for the httpOnly refresh cookie, which
    # in turn forbids the "*" origin wildcard - hence the explicit list.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", tags=["meta"], summary="Liveness probe")
    async def healthz() -> dict[str, str]:
        """Liveness only - deliberately does not touch the database.

        A DB-dependent readiness probe belongs on a separate endpoint so a
        transient Postgres blip cannot get the whole process restarted.
        """
        return {"status": "ok", "environment": settings.ENVIRONMENT}

    app.include_router(api_router)
    # `/api/admin/*` is mounted separately from `api_router` (not nested
    # under `/api/v1`) - it carries its own `AuditLoggingRoute` route class
    # and its own `require_platform_admin` gate, and its prefix is baked
    # into the router itself.
    app.include_router(admin_router)
    return app


app = create_app()
