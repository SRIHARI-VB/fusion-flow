import uuid
from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from fusionflow.config import get_settings

settings = get_settings()

# create_async_engine() does not open a connection - the pool is lazily
# populated on first use. This is required so the app can boot (and
# /healthz can respond) even when Postgres is unreachable; a live
# connection is only attempted the first time a request actually touches
# the database.
# Deliberately `runtime_database_url`, not `DATABASE_URL` directly: the
# running app must query as the low-privilege, non-BYPASSRLS role for RLS
# to apply to it at all. Alembic (alembic/env.py) is the one place that
# still uses DATABASE_URL directly, since migrations need the
# owner/admin role's DDL rights. See config.py::RUNTIME_DATABASE_URL.
engine = create_async_engine(settings.runtime_database_url, pool_pre_ping=True, future=True)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)

# Key under which the active tenant id is stashed on `session.info`.
TENANT_CONTEXT_KEY = "fusionflow_tenant_id"


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a request-scoped AsyncSession."""
    async with async_session_factory() as session:
        yield session


async def set_tenant_context(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Scope the current transaction to a single tenant for RLS.

    Uses `SET LOCAL`, never plain `SET`. Async SQLAlchemy sessions run on
    top of a pooled connection that is returned to the pool (and later
    reused by a *different* request) as soon as the session closes.
    `SET` would persist the GUC on that physical connection past the end
    of the current transaction, silently leaking one request's tenant_id
    into a future request served over the same connection. `SET LOCAL`
    is scoped to the current transaction only and is automatically reset
    on COMMIT/ROLLBACK, so it can never leak across requests.

    `SET LOCAL` cannot be parameterised via the extended query protocol's
    bind parameters (Postgres rejects a bind parameter in that position),
    so the value has to be interpolated into the SQL string directly.
    That is only safe because `tenant_id` is required to already be a
    `uuid.UUID` instance (not a raw caller-controlled string) - `str()`
    of a UUID object can only ever produce the fixed
    8-4-4-4-12 hex-and-hyphen form, so this cannot be used for SQL
    injection.
    """
    if not isinstance(tenant_id, uuid.UUID):
        raise TypeError("tenant_id must be a uuid.UUID instance")
    await session.execute(text(f"SET LOCAL app.current_tenant_id = '{tenant_id}'"))
    # Remembered so `commit_and_keep_tenant_context` can restore it - see below.
    session.info[TENANT_CONTEXT_KEY] = tenant_id


async def commit_and_keep_tenant_context(session: AsyncSession) -> None:
    """COMMIT, then re-apply the tenant GUC for the next transaction.

    The flip side of using `SET LOCAL`: it is discarded at COMMIT along
    with the transaction. A handler that commits half-way through and then
    keeps querying would silently see zero rows (RLS filtering, not an
    error - see the plan's Risk #2). Prefer committing exactly once at the
    end of a request; when that is not possible, commit through this
    helper instead of `session.commit()`.
    """
    await session.commit()
    tenant_id = session.info.get(TENANT_CONTEXT_KEY)
    if tenant_id is not None:
        await set_tenant_context(session, tenant_id)
