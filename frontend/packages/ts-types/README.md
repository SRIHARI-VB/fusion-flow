# @fusion-flow/ts-types

Hand-written shared TypeScript types mirroring the phase-1 backend API contract (auth,
businesses, memberships, JWT claim shape). Consumed directly from source (`src/index.ts`) by
`frontend/web` and `frontend/admin` via npm workspaces — same no-build-step rationale as
`@fusion-flow/ui` (see that package's README).

This package is a placeholder for a future **OpenAPI-generated** TS client (per the plan's
`frontend/packages/ts-types` description: "OpenAPI-generated TS client + shared types"). Once
the backend exposes enough stable endpoints and an OpenAPI schema, regenerate this package
(e.g. via `openapi-typescript`) and keep only the genuinely hand-written types (like the
decoded-JWT claim shape, which does not appear in any HTTP response body) here.
