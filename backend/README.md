# fusion-flow — backend

FastAPI service for the fusion-flow multi-tenant SaaS platform.

**Wave 0 scope**: the foundation only — app factory, configuration, the
async SQLAlchemy/RLS scaffold, core primitives (security, encryption,
pluggable cache and job queue), and the M1 auth + tenancy modules. Custom
fields, the fixed connectors, the connector framework and the workflow
engine are later waves and are deliberately **not** here.

---

## Layout

```
backend/
├── alembic.ini
├── alembic/
│   ├── env.py                      # async-capable, reads DATABASE_URL from Settings
│   └── versions/
│       ├── 0001_initial.py         # users, businesses, memberships, refresh_tokens
│       └── 0002_rls_smoke_test.py  # throwaway table that proves RLS works
├── pyproject.toml
├── .env.example
├── src/fusionflow/
│   ├── main.py                     # app factory, CORS, /healthz, mounts /api/v1
│   ├── api.py                      # /api/v1 router group
│   ├── config.py                   # pydantic-settings Settings
│   ├── db/
│   │   ├── base.py                 # DeclarativeBase, TimestampMixin, TenantScopedMixin
│   │   ├── session.py              # async engine/sessionmaker + SET LOCAL tenant context
│   │   ├── rls.py                  # enable_tenant_rls() helper for migrations
│   │   └── models.py               # single import point for every ORM class
│   ├── core/
│   │   ├── security.py             # argon2 hashing, JWT encode/decode, refresh tokens
│   │   ├── deps.py                 # get_current_user / get_tenant_context / require_role
│   │   ├── cache.py                # CacheBackend protocol + InMemory + Redis
│   │   ├── jobs.py                 # JobQueue protocol + InProcessAsyncQueue + Celery stub
│   │   └── encryption.py           # Fernet envelope encryption + redact_preview
│   └── modules/
│       ├── auth/                   # models, schemas, service, router, http helpers
│       └── tenancy/                # businesses + memberships
└── tests/
    ├── test_app_smoke.py           # offline boot contract
    ├── test_core_units.py          # offline unit tests
    └── test_rls_isolation.py       # requires a live Postgres (see below)
```

## Requirements

- Python 3.11+ (developed against 3.13)
- **PostgreSQL 14+** — required for anything that touches the database.
  Tenant isolation is enforced by Postgres row-level security, so there is
  no SQLite fallback; a SQLite "dev mode" would silently have no isolation
  at all, which is worse than not running.

Redis and Celery are **optional extras** and are never imported at module
level. With `REDIS_ENABLED=false` and `BACKGROUND_JOBS_ENABLED=false`
(the defaults) the app runs entirely on `InMemoryCacheBackend` and
`InProcessAsyncQueue`, and neither package needs to be installed.

## Setup

```bash
cd backend

python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate

pip install -e ".[dev]"          # core + test deps
# optional, only if you want them:
#   pip install -e ".[dev,redis]"
#   pip install -e ".[dev,celery]"

cp .env.example .env             # then edit DATABASE_URL / JWT_SECRET
```

> On Windows, avoid creating `.venv` inside a OneDrive-synced folder — the
> sync client locks files mid-install and pip fails with `WinError 32`.
> Point the venv somewhere local (e.g. `python -m venv %LOCALAPPDATA%\Temp\ff-venv`)
> if you hit that.

### Database roles

Create two roles. This matters: **Postgres table owners bypass RLS unless
`FORCE ROW LEVEL SECURITY` is set, and superusers bypass it always.** The
API must run as a low-privilege, non-owner, non-superuser role or the
isolation policies are decorative.

```sql
CREATE DATABASE fusionflow;

-- migration/owner role (used by alembic)
CREATE ROLE fusionflow_owner LOGIN PASSWORD 'change-me';
ALTER DATABASE fusionflow OWNER TO fusionflow_owner;

-- runtime role (used by the API and by the tests)
CREATE ROLE fusionflow_app LOGIN PASSWORD 'change-me';
GRANT CONNECT ON DATABASE fusionflow TO fusionflow_app;
GRANT USAGE ON SCHEMA public TO fusionflow_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fusionflow_app;
ALTER DEFAULT PRIVILEGES FOR ROLE fusionflow_owner IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO fusionflow_app;
```

### Migrate

```bash
# run as the owner role
alembic upgrade head
```

Useful without a database: `alembic upgrade head --sql` renders the full
DDL to stdout offline.

### Run

```bash
uvicorn fusionflow.main:app --reload --port 8000
```

- Swagger UI: <http://localhost:8000/docs>
- ReDoc: <http://localhost:8000/redoc>
- Health: <http://localhost:8000/healthz>

CORS is preconfigured for the frontend dev servers on
`http://localhost:5173` (`frontend/web`) and `http://localhost:5174`
(`frontend/admin`), with credentials enabled so the httpOnly refresh
cookie works.

## Tests

```bash
pytest                # offline suite; Postgres-dependent tests auto-skip
pytest -v -m needs_postgres   # only the DB-backed tests
```

### Running the RLS isolation test

`tests/test_rls_isolation.py` is the M1 "done when" gate: it proves tenant A
cannot read tenant B's rows through a raw, unfiltered `SELECT *`, that the
symmetric case holds, that a session with **no** tenant context sees zero
rows (not an error, not everything), and that a cross-tenant INSERT is
rejected by the policy's `WITH CHECK`.

It is skipped unless `TEST_DATABASE_URL` is set:

```bash
# 1. a throwaway database, migrated
createdb fusionflow_test
DATABASE_URL=postgresql+asyncpg://fusionflow_owner:pw@localhost:5432/fusionflow_test \
  alembic upgrade head

# 2. point the tests at the LOW-PRIVILEGE role (not owner, never superuser)
export TEST_DATABASE_URL=postgresql+asyncpg://fusionflow_app:pw@localhost:5432/fusionflow_test
pytest tests/test_rls_isolation.py -v
```

PowerShell equivalent for step 2:

```powershell
$env:TEST_DATABASE_URL = "postgresql+asyncpg://fusionflow_app:pw@localhost:5432/fusionflow_test"
pytest tests/test_rls_isolation.py -v
```

The test asserts up front that the connection is not a superuser and fails
with an explanatory message if it is.

## What was and was not verified

Verified in the authoring environment (Python 3.13.2, no database):

- `pip install -e ".[dev]"` succeeds with core dependencies only.
- `python -c "import fusionflow.main"` succeeds with **neither `redis` nor
  `celery` installed** and `REDIS_ENABLED=false` — the Wave 0 boot contract.
- `uvicorn fusionflow.main:app` starts and serves `/healthz` and `/docs`.
- The offline test suite passes.
- `alembic history` shows a single head and `alembic upgrade head --sql`
  renders the complete DDL for both revisions, including the RLS policy.

**Not** verified, because no PostgreSQL, `psql`, `pg_isready` or `docker`
was available in that environment:

- `alembic upgrade head` against a live database.
- `tests/test_rls_isolation.py` — written and reviewed, but **never
  executed**. Run it with the commands above before trusting the isolation
  guarantee.
- Any request path that touches the database (signup/login/refresh/switch).

## Design notes

**`SET LOCAL`, not `SET`.** `db/session.py::set_tenant_context` issues
`SET LOCAL app.current_tenant_id = '<uuid>'`. Async sessions sit on pooled
connections that are handed to a *different* request once the session
closes; a plain `SET` would persist the GUC on that physical connection and
leak one tenant's context into the next request. `SET LOCAL` is
transaction-scoped and resets on COMMIT/ROLLBACK.

The flip side: committing mid-request discards the GUC. Prefer one commit
at the end of a request; where that is impossible use
`db/session.py::commit_and_keep_tenant_context`.

**Platform vs. tenant-scoped tables.** `users`, `businesses`,
`memberships` and `refresh_tokens` carry no RLS policy — they are read
during login and business-switch, before any tenant context exists. The
reasoning (including the `memberships` judgment call) is documented at the
top of `alembic/versions/0001_initial.py`. Every *tenant-scoped* table
added in a later wave must use `TenantScopedMixin` and call
`enable_tenant_rls(op, "<table>")` in its migration.

**`_rls_smoke_test`.** A throwaway table created solely so Wave 0 has
something to point the isolation test at. Once a real tenant-scoped table
exists, re-point the test at it and drop this table in a new migration.

**Secrets.** `ENCRYPTION_KEY` in `.env.example` is a fixed dev value and is
**not production-safe**. `core/encryption.py` already carries the
`encryption_key_version` convention so a KMS-backed rotation can be dropped
in without a data migration.
