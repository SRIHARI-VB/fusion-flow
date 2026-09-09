# frontend/web

Tenant-facing fusion-flow app (Vite + React + TypeScript). Onboarding, dashboard, the fixed
connectors (products/services/coupons/offers, customers/orders/payments, tickets/kb),
connectors, workflows, and settings — most non-dashboard/non-auth routes are "coming soon"
placeholder shells in this wave (see the architecture plan's phased roadmap).

## Package manager note

The architecture plan specifies **pnpm workspaces**. `pnpm` is not installed in this sandbox,
so this repo uses **npm workspaces** instead: the repo root `package.json` declares
`"workspaces": ["frontend/web", "frontend/admin", "frontend/packages/*"]`, and there is no
`pnpm-workspace.yaml`. Functionally equivalent for this project's needs (hoisted
`node_modules`, symlinked local packages). Swap back to pnpm later by adding
`pnpm-workspace.yaml` and removing the root `package.json` `workspaces` field, if desired.

## Setup

From the **repo root** (not this directory) — npm workspaces install for all workspaces at once:

```bash
npm install
```

## Run (dev)

```bash
npm run dev --workspace=web
# or: cd frontend/web && npm run dev
```

Runs on http://localhost:5173 by default.

## Build

```bash
npm run build --workspace=web
```

Runs `tsc --noEmit` (full type-check across the app and the workspace packages it imports)
followed by `vite build`.

## Environment variables

Copy `.env.example` to `.env` and adjust as needed:

- `VITE_API_URL` — base URL of the backend FastAPI service (e.g. `http://localhost:8000`).
  No live backend is required to build or browse the placeholder/dashboard UI — only real
  login/signup network calls need it running.

## Security note: access tokens never touch localStorage

The JWT access token is held **only** in an in-memory Zustand store
(`src/lib/auth-store.ts`) — never written to `localStorage`/`sessionStorage`. This is a hard
requirement from the architecture plan. The refresh token is an opaque value in an httpOnly
cookie set by the backend and is never readable from JS. `src/lib/api-client.ts` wires an
axios response interceptor that, on a `401`, calls `POST /api/v1/auth/refresh` with
`withCredentials: true` and retries the original request once.

## Architecture notes

- `src/lib/api-client.ts` — axios instance + auth header/refresh-retry interceptors.
- `src/lib/auth-store.ts` — in-memory session state (Zustand).
- `src/lib/endpoints.ts` — typed wrappers for the `/api/v1/auth/*` and `/api/v1/businesses/*`
  endpoints documented in the architecture plan.
- `src/lib/jwt.ts` — client-side (unverified) JWT payload decode, used only to read
  `tenant_id`/`platform_admin` for routing decisions, never for authorization.
- Login handles both the direct-to-tenant response and the multi-membership "pre-tenant"
  response (no `business`/`tenant_id`) by routing to `/select-business`, which calls
  `GET /businesses/mine` then `POST /businesses/{id}/switch`.
- Dashboard trend panel uses a hand-rolled CSS/flexbox bar chart (see root task report for
  rationale) rather than a charting library.
