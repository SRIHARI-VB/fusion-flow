"""Cross-tenant isolation test — the plan's M1 "done when" criterion.

Proves that tenant separation is enforced by **Postgres**, not by
application-side filtering: every assertion below runs a bare
`SELECT * FROM _rls_smoke_test` with no WHERE clause, so the only thing
that can shrink the result set is the `tenant_isolation` RLS policy.

Cases:
  1. tenant A context  -> sees exactly tenant A's rows
  2. tenant B context  -> sees exactly tenant B's rows (symmetric)
  3. no tenant context -> sees ZERO rows, and does not raise. This is the
     FORCE ROW LEVEL SECURITY behaviour: `current_setting(..., true)`
     returns NULL when unset, `tenant_id = NULL` evaluates to NULL, and a
     non-true policy predicate filters the row out silently. That silent
     empty result - not an error - is exactly the failure mode flagged as
     Risk #2 in the architecture plan, so it is pinned down here.
  4. cross-tenant INSERT -> rejected by the policy's WITH CHECK clause.

!! STATUS: WRITTEN BUT NEVER EXECUTED !!
The environment this was authored in had no Postgres, psql, pg_isready or
docker, so this file has been reviewed for correctness but never run. See
backend/README.md -> "Running the RLS isolation test" for the exact
commands to execute it for real.

Two prerequisites that will otherwise make this test lie:
  * `alembic upgrade head` must have been applied (needs revision
    0002_rls_smoke_test).
  * `TEST_DATABASE_URL` must connect as a **non-superuser** role, since
    superusers bypass RLS even with FORCE enabled. Asserted below rather
    than left to produce a confusing failure.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.db.session import set_tenant_context
from tests.conftest import requires_postgres

pytestmark = [pytest.mark.asyncio, pytest.mark.needs_postgres, requires_postgres]


async def _assert_not_superuser(session: AsyncSession) -> None:
    is_superuser = (
        await session.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user"))
    ).scalar_one()
    assert not is_superuser, (
        "TEST_DATABASE_URL connects as a Postgres superuser. Superusers bypass "
        "row-level security even with FORCE ROW LEVEL SECURITY, so this test "
        "would pass or fail meaninglessly. Point it at a dedicated "
        "low-privilege role - the same kind of role the API runs as in "
        "production."
    )


async def _labels_visible(session: AsyncSession) -> set[str]:
    """Deliberately unfiltered: no WHERE clause, so RLS is the only filter."""
    rows = await session.execute(text("SELECT * FROM _rls_smoke_test"))
    return {row.label for row in rows}


@pytest.fixture
async def tenants(pg_session_factory):
    """Two businesses, each with rows in `_rls_smoke_test`. Cleaned up after.

    `businesses` is a platform table with no RLS policy, so those rows go in
    without any tenant context. The `_rls_smoke_test` inserts DO need
    context, because the policy's WITH CHECK clause applies to writes too -
    which is itself part of what makes the isolation trustworthy.
    """
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    async with pg_session_factory() as session:
        await _assert_not_superuser(session)
        for tenant_id, name in ((tenant_a, "RLS Tenant A"), (tenant_b, "RLS Tenant B")):
            await session.execute(
                text(
                    "INSERT INTO businesses (id, name, slug, status) "
                    "VALUES (:id, :name, :slug, 'active')"
                ),
                {"id": tenant_id, "name": name, "slug": f"rls-{tenant_id.hex[:12]}"},
            )
        await session.commit()

    for tenant_id, labels in ((tenant_a, ("a-one", "a-two")), (tenant_b, ("b-one",))):
        async with pg_session_factory() as session:
            await set_tenant_context(session, tenant_id)
            for label in labels:
                await session.execute(
                    text(
                        "INSERT INTO _rls_smoke_test (id, tenant_id, label) "
                        "VALUES (:id, :tenant_id, :label)"
                    ),
                    {"id": uuid.uuid4(), "tenant_id": tenant_id, "label": label},
                )
            await session.commit()

    yield tenant_a, tenant_b

    async with pg_session_factory() as session:
        # ON DELETE CASCADE from businesses removes the smoke rows too, so
        # this works without needing tenant context for the child table.
        await session.execute(
            text("DELETE FROM businesses WHERE id = ANY(:ids)"), {"ids": [tenant_a, tenant_b]}
        )
        await session.commit()


async def test_tenant_a_sees_only_its_own_rows(pg_session_factory, tenants) -> None:
    tenant_a, _ = tenants
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        assert await _labels_visible(session) == {"a-one", "a-two"}


async def test_tenant_b_sees_only_its_own_rows(pg_session_factory, tenants) -> None:
    """Symmetric to tenant A - rules out an accidentally one-way policy."""
    _, tenant_b = tenants
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_b)
        assert await _labels_visible(session) == {"b-one"}


async def test_no_tenant_context_sees_zero_rows(pg_session_factory, tenants) -> None:
    """No SET LOCAL at all: zero rows, no exception, no leakage."""
    async with pg_session_factory() as session:
        assert await _labels_visible(session) == set()


async def test_cross_tenant_insert_is_rejected(pg_session_factory, tenants) -> None:
    """WITH CHECK blocks writing a row belonging to a different tenant."""
    tenant_a, tenant_b = tenants
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        with pytest.raises(DBAPIError):
            await session.execute(
                text(
                    "INSERT INTO _rls_smoke_test (id, tenant_id, label) "
                    "VALUES (:id, :tenant_id, :label)"
                ),
                {"id": uuid.uuid4(), "tenant_id": tenant_b, "label": "smuggled"},
            )
        await session.rollback()
