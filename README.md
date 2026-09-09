# fusion-flow

Multi-tenant SaaS platform: businesses configure custom fields, connectors (messaging, payments, calendar/mail, support), and visual automation workflows. Includes a separate super-admin panel for platform operators.

## Repo layout

- `frontend/web` — tenant-facing app (onboarding, dashboard, connectors, workflow builder)
- `frontend/admin` — super admin app (separate build, own subdomain)
- `frontend/packages` — shared UI kit, generated API types, workflow node schemas
- `backend` — FastAPI service (auth, tenancy, custom fields, connectors, workflow engine, admin API)
- `docs/design` — UI/workflow visual reference used to build the frontend
- `docs/adr` — architecture decision records
- `infra` — local dev infra (docker-compose, env templates)

## Stack

React + TypeScript, Tailwind + shadcn/ui, React Hook Form + Zod, TanStack Query, @xyflow/react · FastAPI + Pydantic + SQLAlchemy on Supabase Postgres, Alembic, Row-Level Security for tenant isolation · Redis cache and Celery/Redis Streams jobs are provisioned behind swappable interfaces and disabled in dev · optional AI (LangChain + LangGraph) is feature-flag gated and never required for deterministic workflows.

## Status

Phase 1 build in progress. See the architecture and phased roadmap for details.

## Local development

See `backend/README.md` and `frontend/web/README.md` (added as each part is scaffolded) for setup instructions.
