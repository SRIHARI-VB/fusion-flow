# frontend/admin

Super-admin app (separate Vite entry/build/subdomain per the architecture plan). This wave
only implements the login page (with a hard client-side gate on the decoded JWT's
`platform_admin` claim — a non-admin credential that authenticates successfully still gets
rejected here) and a `/tenants` placeholder page built from `@fusion-flow/ui` (Card + Table +
Badge + Button), proving the shared package works identically across both apps.

## Run

```bash
npm install               # from repo root
npm run dev --workspace=admin
```

Dev server on http://localhost:5174 (frontend/web uses 5173). Env var: `VITE_API_URL` (see
`.env.example`) — same backend, `/api/v1/auth/login` endpoint.

`/audit-log`, `/feature-flags`, `/templates`, `/billing`, and `/tenants/:id` from the plan's
route list are not built in this wave — only `/tenants` and `/login` per this task's scope.
