"""Shared pytest fixtures.

Tests split into two groups:

* Offline tests (default) - no external service required. They run
  everywhere, including CI with no database.
* `requires_postgres` tests - need a live Postgres reachable via
  `$TEST_DATABASE_URL` with `alembic upgrade head` already applied. They
  skip (rather than fail) when that variable is unset.

A dedicated variable, not `DATABASE_URL`, so nobody can point the
destructive isolation test at a dev database by accident.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Registers every ORM class with SQLAlchemy's mapper registry before any
# test runs - without this, running a single test file in isolation
# (rather than the full suite, where some other test file happens to
# import this first) can hit `sqlalchemy.exc.InvalidRequestError:
# ... failed to locate a name ('User')` the first time any model with a
# string-based relationship (e.g. `Membership.user`) is instantiated,
# since SQLAlchemy only resolves those lazily, on first use, against
# whatever has been imported *so far*. Matches `fusionflow.main`'s own
# `from fusionflow.db import models as _models` import-for-side-effect.
from fusionflow.db import models as _models  # noqa: E402, F401

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

requires_postgres = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason=(
        "TEST_DATABASE_URL is not set - set it to a real Postgres instance "
        "(with `alembic upgrade head` already applied against it) to run "
        "the RLS isolation test. Example: "
        "postgresql+asyncpg://fusionflow_app:...@localhost:5432/fusionflow_test"
    ),
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "needs_postgres: requires a live Postgres via $TEST_DATABASE_URL with migrations applied",
    )


@pytest_asyncio.fixture
async def pg_session_factory():
    """Session factory against TEST_DATABASE_URL.

    Uses the default connection pool on purpose: connections ARE reused
    across the sessions the isolation test opens, which is exactly the
    condition under which a plain `SET` (instead of `SET LOCAL`) would leak
    one tenant's context into the next session.

    Only used by tests marked `requires_postgres`; the fixture is never
    evaluated - and never tries to connect - when that mark skips the test,
    since pytest skips before fixture setup.
    """
    if not TEST_DATABASE_URL:  # pragma: no cover - guarded by requires_postgres
        pytest.skip("TEST_DATABASE_URL not set")
    engine = create_async_engine(TEST_DATABASE_URL)
    yield async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def pg_session(pg_session_factory):
    """A single session against TEST_DATABASE_URL.

    IMPORTANT: TEST_DATABASE_URL must authenticate as the low-privilege
    runtime application role, not the migration/owner role and never a
    superuser - Postgres superusers bypass RLS entirely, even with FORCE
    ROW LEVEL SECURITY, which would make the isolation test pass or fail
    for the wrong reason. The test asserts this up front.
    """
    async with pg_session_factory() as session:
        yield session
