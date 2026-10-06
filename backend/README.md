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

### Database: Docker (recommended for local dev)

```bash
docker compose -f ../infra/docker/docker-compose.dev.yml up -d
```

This starts a disposable local Postgres matching `.env.example`'s defaults
exactly (`DATABASE_URL=postgresql+asyncpg://fusionflow:fusionflow@localhost:5432/fusionflow`)
and creates the low-privilege `fusionflow_app` role automatically on first
boot (`infra/docker/initdb/01-create-app-role.sql`) with the
`RUNTIME_DATABASE_URL` from `.env.example` already matching its password
(`fusionflow_app_dev_only`). Nothing else to configure — copy `.env.example`
to `.env`, uncomment `RUNTIME_DATABASE_URL`, and skip straight to Migrate
below.

To start over: `docker compose -f ../infra/docker/docker-compose.dev.yml down -v`
(the `-v` drops the data volume, so the init script re-runs and re-creates
the role on next `up`).

### Database: manual setup (no Docker, or a shared/remote Postgres)

Create two roles. This matters: **Postgres table owners bypass RLS unless
`FORCE ROW LEVEL SECURITY` is set, and superusers (and, on managed
providers like Supabase, any role with `rolbypassrls=true` — check for
this explicitly, it is not the same as superuser) bypass it always.** The
API must run as a low-privilege, non-owner, non-superuser, non-bypassrls
role or the isolation policies are decorative.

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

If you change the API port, update `BACKEND_PUBLIC_BASE_URL` and both
frontend apps' `VITE_API_URL` values to match.

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

It is skipped unless `TEST_DATABASE_URL` is set.

**Using the Docker compose Postgres**: it already has the low-privilege
role, so this is just:

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://fusionflow_app:fusionflow_app_dev_only@localhost:5432/fusionflow
pytest tests/test_rls_isolation.py -v
```

**Manual Postgres**:

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

### Instagram `/clear`

An exact `/clear` DM (case-insensitive, surrounding whitespace allowed)
cancels that sender's active conversation on the receiving Instagram
connection. It clears suspended answers and removes all of that sender's
Instagram-created `draft`, `requested` and `confirmed` appointment records,
including bookings from completed workflow runs. Exact workflow provenance
scopes deletion to the tenant, Instagram connection and sender. Manual/other-
channel bookings, completed appointments, patient profiles, tickets and
message/run history remain. Completed clinical visits protect their linked
appointments even if the appointment status is stale. Other visits retain
their clinical notes and patient detail snapshots, with the deleted booking
reference detached. Non-appointment drafts from cancelled runs are also removed.

Linked Google Calendar cancellations are queued in the same transaction as
booking deletion. These idempotent DELETEs retry with backoff on subsequent
webhooks/poller passes; a revoked token still needs the calendar reconnected.
The reset acknowledgement says calendar synchronization is queued rather than
claiming Google has already deleted the event. Ordinary Instagram sends and
failed workflows are never automatically replayed by this retry path.

The bot acknowledges the reset and asks the sender to send `Hi`. The next
message carries `trigger.conversation_reset = true`; the clinic workflow
routes it to its initial welcome regardless of whether the patient already
exists. A successful fresh run consumes the flag. Earlier message/button
deliveries are ignored using their original timestamps. Normal later
conversations retain the returning-patient greeting.

Deploy migration `0039_conversation_reset` before deploying the backend.
For the existing clinic graph, run the guarded repair in dry-run mode first:

```bash
python scripts/repair_clinic_instagram_workflow.py \
  --tenant-id TENANT_UUID --workflow-id WORKFLOW_UUID \
  --actor-email OWNER_EMAIL --expected-version CURRENT_VERSION \
  --enable-conversation-reset
```

Add `--apply` after validation to publish a new version. The script preserves
the previous published version and never executes the workflow or sends DMs.

Reset integration tests require a disposable migrated `TEST_DATABASE_URL`
using a non-superuser, non-BYPASSRLS role; provider calls are mocked:

```bash
pytest tests/test_instagram_conversation_reset.py tests/test_instagram_reset_postgres.py
```

### Instagram button menus and calendar reconnection

`send_button_template` splits an option list into ordered messages containing
at most three postback buttons. Titles are capped at 20 characters; payloads
stay unchanged. The first message carries the prompt and later messages say
"More options:". A partially delivered menu is not automatically replayed.
`instagram.ask_choice` supports up to 100 module options; calendar-slot pickers
support up to 288 slots, independently of the three-button message limit.

Deploy the updated backend before upgrading the clinic graph. Run from
`backend` with the configured environment (read-only unless `--apply` is added):

```bash
python -m scripts.upgrade_clinic_button_menus \
  --tenant-id TENANT_UUID --workflow-id WORKFLOW_UUID \
  --actor-email OWNER_EMAIL --expected-version CURRENT_VERSION
```

This preserves existing routing and `/clear`, removes the welcome typing hint,
and replaces the two hardcoded service pages with one dynamic picker.

Google `invalid_grant` marks the connector **Action required** and stops workflow
retries. Slot selection sends a patient-facing unavailability message and stops
before any booking confirmation. Reconnect through **Connectors → Google
Calendar → Connect with Google**, using the account that owns the calendar;
the app stores the new tokens automatically. No token needs to be copied.
A revoked refresh token cannot be repaired with code. If the OAuth app is in
Google's external **Testing** mode, grants with Calendar scopes expire after
seven days; review the app's publishing status for an ongoing deployment
([Google OAuth documentation](https://developers.google.com/identity/protocols/oauth2#expiration)).

### Instagram waiting flows and inbox failures

A new `instagram.collect_text` question replaces an older waiting run for the
same tenant, Instagram connector and sender before sending. The old run is
retained as cancelled; customer records and submitted appointments are untouched.
This allows switching from consultation to a treatment while a name is pending
without violating `uq_workflow_runs_waiting_correlation` after a DM was sent.

The dispatcher commits each inbox event independently, reacquiring its tenant
context and ordering lock each time. An unexpected dispatch/flush failure rolls
back only that event's database changes and records `processing_error` with
`processed_at` on its inbox row. It does not automatically replay the event:
external messages may already have been delivered. Review such rows and their
provider effects before any manual replay. Later users continue normally.
This prevents the constraint-error replay loop; it is not a claim of exactly-once
provider delivery across process termination or a database outage during a send.

Apply migration `0040_inbox_processing_error` before deploying this dispatcher.
Regression coverage uses the disposable Postgres database with mocked providers:

```bash
pytest tests/test_instagram_dispatch_postgres.py tests/test_instagram_reset_postgres.py
```

### Clinic patient details and booking reset

Apply `0041_patient_booking_reset` before deploying the backend. It adds visit
name/phone snapshots (backfilled from existing customers) and the cancellation
retry timestamp. Publish the clinic graph using the guarded script below;
omit `--apply` for read-only validation:

```bash
python -m scripts.upgrade_clinic_patient_details \
  --tenant-id TENANT_UUID --workflow-id WORKFLOW_UUID \
  --actor-email OWNER_EMAIL --expected-version CURRENT_VERSION --apply
```

The upgrade asks one name question followed by a phone question on consultation,
treatment and legacy booking branches. All 18 appointment creation paths read
current patient details before saving a booking snapshot; calendar descriptions
include the phone. The script adds optional phone/event-link fields and recovers
old booking provenance and calendar IDs from exact successful step outputs.
It does not execute a workflow or cancel an existing booking. Waiting runs keep
their immutable version; `/clear` followed by `Hi` starts the new version.
Patient Flow quick check-in pre-fills both fields and preserves the appointment's
customer identity while recording the visit's name and phone independently.

### Database and secrets

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
