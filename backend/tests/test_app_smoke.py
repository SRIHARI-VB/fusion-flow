"""Offline boot checks — no Postgres, Redis or Celery required.

These encode the Wave 0 boot contract: the app must import and serve
/healthz with `REDIS_ENABLED=false` and the optional `redis`/`celery`
packages absent from the environment.
"""

from __future__ import annotations

import httpx
import pytest

from fusionflow.api import API_V1_PREFIX
from fusionflow.main import app, create_app


async def test_healthz_returns_ok() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_openapi_exposes_the_v1_auth_and_business_routes() -> None:
    paths = set(app.openapi()["paths"])
    for route in (
        "/auth/signup",
        "/auth/login",
        "/auth/refresh",
        "/auth/logout",
        "/auth/select-business",
        "/auth/me",
        "/businesses/mine",
        "/businesses/{business_id}",
    ):
        assert f"{API_V1_PREFIX}{route}" in paths, f"missing route {route}"


def test_cors_allows_both_frontend_dev_origins() -> None:
    origins = create_app().state.settings.cors_origins_list
    assert "http://localhost:5173" in origins
    assert "http://localhost:5174" in origins


def test_optional_backends_are_not_hard_dependencies() -> None:
    """`redis`/`celery` must not be imported as a side effect of booting."""
    import sys

    assert "redis" not in sys.modules
    assert "celery" not in sys.modules


def test_celery_queue_is_an_explicit_stub() -> None:
    from fusionflow.core.jobs import CeleryQueue

    with pytest.raises(NotImplementedError, match="BACKGROUND_JOBS_ENABLED=false"):
        CeleryQueue()
