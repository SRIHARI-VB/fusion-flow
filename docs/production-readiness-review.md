# fusion-flow — Production-Readiness & Security Review

Date: 2026-10-01. Scope: backend (FastAPI), frontend/web (tenant app), frontend/admin (platform admin). Working tree reviewed **including uncommitted changes** (role-module restrictions, communication gating, revoke-impact flow). Read-only review; no code changed.

Findings were produced by six parallel code reviews (auth/tenancy/admin, route permission matrix, non-auth security surface, workflow engine + business modules, web frontend, admin frontend) and spot-verified. Items marked *(unverified)* were reasoned from code but not executed.

---

## 1. Verdict

**Not production-ready yet, but the foundation is strong.** Tenant isolation (RLS + per-request DB re-verification of membership/role), credential encryption, OAuth state handling, HMAC verification where configured, and the new per-role module restriction layer are all correctly built. The blockers are concentrated in five places:

1. **Fail-open secrets**: webhooks accepted unverified when a tenant omits `app_secret`; cron endpoint open when `CRON_SECRET` is unset; RLS silently bypassed if `RUNTIME_DATABASE_URL` is unset.
2. **Token-type confusion**: step-up tokens and impersonation tokens are accepted by `CurrentUserDep` routes and can be exchanged for full 30-day sessions.
3. **Role model is two-tier only**: below Owner/Admin every Member can do everything in a module — publish automations, blast WhatsApp, create payment rows, delete customers (which cascades into orders, payments and patient visits), and re-apply the business template to change the tenant's module bundle and plan.
4. **Poller reliability**: a single bad inbox row re-sends messages forever; a failed broadcast re-fires every 30 s; the appointment-reminder poller sends only the first reminder per tenant per pass.
5. **Operational gaps**: no rate limiting, no CI, no lockfile, no security headers, no member removal/role change/password reset, no error boundaries in either frontend.

---

## 2. Findings (deduplicated, ranked)

Path prefix `B/` = `backend/src/fusionflow/`, `W/` = `frontend/web/src/`, `A/` = `frontend/admin/src/`.

### 2.1 Critical — must fix before any production traffic

| # | Finding | Where | Fix |
|---|---|---|---|
| C1 | **Inbound webhooks accepted unverified** when the tenant did not supply `app_secret` and no global secret is set. `app_secret` is optional in every Meta/Telegram config schema and stored as `""`. Forged payloads create inbox messages, fire triggers, resume `ask_*` waits and cause outbound sends at the tenant's cost. | `B/modules/connectors/whatsapp/adapter.py:821-893`, `instagram/adapter.py:1153-1221`, `facebook/adapter.py:316-384`, `telegram/adapter.py:302-365` | Make the secret required at connect (or refuse boot outside dev unless global `*_WEBHOOK_APP_SECRET` is set); `resolve_instance_for_webhook` returns `None` when no secret exists; add to `validate_secrets_for_environment`. |
| C2 | **`/api/v1/internal/scheduled-tasks` is open when `CRON_SECRET` is unset** (warn-and-allow), compares with `!=`, and the feedback/reminder pollers it runs have no `FOR UPDATE SKIP LOCKED`, so overlapping hits double-send DMs. | `B/modules/workflows/engine/internal_router.py:54-63`, `feedback_poller.py`, `appointment_reminder_poller.py` | Fail boot when `not is_development and CRON_SECRET is None`; `hmac.compare_digest`; mount only when `is_serverless`; advisory lock or `SKIP LOCKED` in both pollers. |
| C3 | **Impersonation tokens can be laundered into normal sessions.** `impersonated`/`acting_admin_id` claims are never read. `POST /auth/select-business` and `/businesses/{id}/switch` accept any `CurrentUserDep` token and mint an unflagged access token **and a 30-day refresh family** for any business the target belongs to. Targets may be platform admins. `ImpersonationSession.ended_at` is never set; no tenant-side audit. | `B/modules/admin/service.py:532-613`, `B/modules/auth/router.py:109-124`, `B/modules/tenancy/router.py:146-163` | Add a `typ` claim; reject `impersonated` tokens on select-business/switch/refresh/step-up; refuse `is_platform_admin` targets; add end-impersonation that sets `ended_at` and check it in `get_tenant_context`; log `target_user_id` in audit. |
| C4 | **Step-up JWT is accepted as a bearer access token.** `decode_access_token` is a bare `jwt.decode`; a step-up token (45-min TTL, same secret) passes `get_current_user` and can call `select-business` to obtain a full session. | `B/core/security.py:65-67, 92-122`, `B/core/deps.py:53-71` | Add `typ: "access"` / `typ: "step_up"` claims and require them in each decoder (`options={"require": [...]}`), reject `step_up is True` in `decode_access_token`. |
| C5 | **Any Member can re-apply a business template**, which rewrites the tenant's module bundle and silently assigns `plan_id`. Also flips grandfathered access. | `B/modules/business_templates/router.py:107-143`, `B/modules/connectors/service.py:137-154, 258-271` | `require_role(OWNER)` + owner step-up at minimum; preferably platform-admin only (route already exists under `/api/admin`). |
| C6 | **Deleting a customer cascades to orders, payments (incl. captured) and patient visits (consultation notes)**; `DELETE /customers/{id}` has no role gate. | `B/modules/orders/models.py:41`, `payments/models.py:52`, `clinic_queue/models.py:60`, `customers/router.py:83` | `ondelete="RESTRICT"` or `SET NULL`; soft-delete customers; `require_role(OWNER, ADMIN)` on delete. |
| C7 | **Outbox poller has no per-row error isolation or dead-letter.** All rows for a tenant run in one transaction; any non-`RunLoopError` exception (KeyError on payload, malformed graph, IntegrityError) rolls back the batch, `processed_at` stays NULL, and already-delivered sends are **re-sent every 2 s forever**. | `B/modules/workflows/engine/outbox_poller.py:203-341` | SAVEPOINT per row, `attempts` counter + cap, `failed_at`/`error` columns, commit per row via `commit_and_keep_tenant_context`. |
| C8 | **Schedule poller advances `next_run_at` only after the run executes in the same transaction.** A 200-recipient broadcast that fails at recipient 150 re-fires on every 30 s pass. | `B/modules/workflows/engine/schedule_poller.py:286-402` | Claim first (set `last_run_at`/`next_run_at`, commit), then execute in a second transaction; record `last_run_status`. |
| C9 | **Reminder poller commits inside its loop after a single `set_tenant_context`**, so from the second record onward RLS hides customers/conversations and only one reminder per tenant per pass is sent (window is 20 min, so the rest are missed). Also hardcodes "Dr. Faheem" and `Asia/Kolkata` for every tenant. | `B/modules/workflows/engine/appointment_reminder_poller.py:103, 150-210`; `feedback_poller.py:75` | Use `commit_and_keep_tenant_context`; template text and timezone from tenant settings. |
| C10 | **`clinic_queue` catalog key is never seeded** (not in `scripts/seed_feature_modules.py`, not in migration 0037), so `require_module_access("clinic_queue")` returns 500 on every Patient Flow route on a fresh DB. | `backend/scripts/seed_feature_modules.py`, `alembic/versions/0037_clinic_queue.py` | Add the catalog row in a migration (data migration, idempotent). |
| C11 | **Admin "Deny" fires even when the reason prompt is cancelled** (`prompt()` returns `null`, coerced to `undefined`, mutation runs). | `A/features/tenants/TenantsPage.tsx:172-173`, `TenantDetailPage.tsx:250-251` | `if (reason === null) return;` or reuse the `Modal` pattern. |

### 2.2 High

**Backend — auth & team**
- H1 **No rate limiting or lockout anywhere** (login, step-up, signup, refresh, webhooks, verify-token scans). `/auth/step-up` lets a holder of a stolen access token brute-force the user's password. `B/modules/auth/router.py`. Add per-IP + per-account sliding windows via `CacheBackend.incr`, lockout after N failures.
- H2 **Refresh token echoed in JSON body** for all clients, defeating the httpOnly cookie against XSS. `SameSite=None` in prod with no CSRF header check on cookie-authenticated `/auth/refresh`/`/auth/logout`. `B/modules/auth/http.py:59, 204-212`. Omit body copy for browser clients; require `X-Requested-With` or Origin check.
- H3 **Team lifecycle is incomplete**: no remove member, no role change, no self-service password change, no password reset, no email verification. Owner/Admin sets and permanently knows the member's password (which doubles as the doctor's step-up proof). Admin can create other Admins. `B/modules/tenancy/router.py:197-319`, `schemas.py:221-226`. Add `DELETE .../members/{id}` (last-owner guard, no self-remove), `PATCH role` (Owner only), `PATCH /auth/me/password` (revoke all refresh tokens), reset + verification flows; revoke refresh tokens on role change/removal.
- H4 **Tenant suspension not enforced on access tokens or refresh.** `get_tenant_context` never checks `Business.status`; `refresh()` only checks membership. `B/core/deps.py:142-197`, `B/modules/auth/service.py:312-397`. Check `status == ACTIVE` in both.
- H5 **`RUNTIME_DATABASE_URL` is not validated**; falls back to `DATABASE_URL` (Supabase `postgres` role has `BYPASSRLS`), silently disabling RLS. `B/config.py:69`, `B/db/session.py:47-53`. Require set and ≠ `DATABASE_URL` outside dev; optionally assert `rolbypassrls = false` at startup.

**Backend — module/team permissions**
- H6 **Member can perform every dangerous action in a module**: publish/delete workflows, create schedules (up to 1000 recipients per fire), create/activate/delete broadcast campaigns, create manual `captured` payment rows with arbitrary amounts, delete customers and media, sync/delete WhatsApp templates, set Instagram ice-breakers. `B/modules/workflows/router.py:193-376`, `broadcast_campaigns/router.py:46-97`, `payments/router.py:24-34`, `customers/router.py:83`, `media_library`, `whatsapp/router.py`, `instagram/router.py`. Gate on `require_role(OWNER, ADMIN)`; keep Member for day-to-day CRUD and draft editing.
- H7 **`GET /connectors/{id}/events` returns raw webhook bodies** (message text, phone numbers) to every role with no module gate; **`POST /connectors/{id}/media` has no module gate**; WhatsApp/Instagram routers are gated on integration keys so the new `communication` role restriction does not cover them. `B/modules/connectors/router.py:278, 331-341`. Stack `require_module_access("communication")` (or redact payload to metadata).
- H8 **Workflow run steps persist the full variable snapshot and node config**, including `http.request` headers (API keys) and every prior response body; returned to any member via `RunDetailOut`; no retention. Storage is O(steps²). `B/modules/workflows/engine/run_loop.py:427-439`, `router.py:286-300`. Redact secrets, store diffs, add a retention job.
- H9 **No opt-out/suppression list, no per-tenant send quota**, `scheduled_at` not validated to be in the future. `B/modules/broadcast_campaigns/service.py:158-235`. Add a suppression table honoured by all send paths; quotas as a plan resource.

**Backend — SSRF / egress**
- H10 **SSRF guard gaps**: `100.64.0.0/10` allowed (Alibaba metadata `100.100.100.200` verified allowed), no response-size cap, IPv4-mapped IPv6 only correct on Python ≥3.13 while pyproject allows ≥3.11; `http.request`/`connector.action` retry non-idempotent calls. `B/modules/workflows/engine/url_safety.py:136-146`, `nodes/http_request.py:62-108`. Block `not ip.is_global`; cap bytes; pin resolved IP via custom transport; retry only idempotent methods.
- H11 **Cloudflare R2 `endpoint_url` is tenant-supplied and not validated** → signed requests to arbitrary internal hosts with a status-code oracle. `B/modules/connectors/cloudflare_r2/adapter.py:187-224, 325-340`. Restrict to `https://<account>.r2.cloudflarestorage.com`.
- H12 **"Stub mode on network failure" is live in production**: Google OAuth fabricates tokens and marks CONNECTED; R2/WhatsApp/Razorpay/Telegram validators assume success on egress failure. `B/modules/connectors/google/oauth.py:161-197`, `cloudflare_r2/adapter.py:218-224`. Stub only when `settings.is_development`.

**Backend — operations**
- H13 **No lockfile, lower-bound pins only, no CI.** Vercel resolves whatever is newest; the webhook `BackgroundTasks` path (`B/modules/connectors/webhooks.py:166`) passes the request-scoped session to a background task and only works because FastAPI ≥0.118 defaults yield-dependencies to request scope (verified in installed 0.141.1; older allowed versions close the session first). Commit a lockfile, pin Python 3.13, add CI; open a fresh session inside the background task.

**Web frontend**
- H14 **Step-up 401s are treated as access-token expiry**: interceptor refreshes on every 401, so an expired doctor step-up token causes refresh-token rotation + retry loops and the password gate is never re-shown; a wrong step-up password is POSTed twice. `W/lib/api-client.ts:63-72`, `W/components/auth/RequireStepUp.tsx:47`. Skip refresh for `/auth/step-up`, `/auth/login` and "Step-up" details; call `clear()` on step-up 401; add an expiry timer.
- H15 **Owner cannot finish onboarding**: `/onboarding` PATCHes `/businesses/{id}` which requires owner step-up, but the route is not wrapped in `RequireStepUp`. `W/App.tsx:71`, `W/features/onboarding/OnboardingPage.tsx:37-45`.
- H16 **Multi-tab refresh race revokes the whole token family** (server has no reuse grace; single-flight is per tab; connector list polls every 15 s per tab). `W/components/auth/AuthBootstrap.tsx:26-35`, `W/lib/api-client.ts:40-58`. Use `navigator.locks` / BroadcastChannel; consider a short server-side grace for the immediately-previous token.
- H17 **Sign-out / business switch do not clear the step-up token or React Query cache**; 70 of 71 query keys carry no tenant id → previous user's data flashes and stale step-up header is sent. `W/components/layout/Sidebar.tsx:153-164`, `W/pages/SelectBusiness.tsx:34-46`.
- H18 **Module-access query failure makes every module look un-entitled** and shows a live "Request access" button to Owners → spurious requests in the admin queue. `W/lib/useModuleAccess.ts:20-26`, `W/components/auth/RequireModule.tsx:15-21`.

**Admin frontend**
- H19 **FastAPI 422 bodies crash the app** (array `detail` rendered as React child), no `ErrorBoundary` anywhere. `A/features/**` (8 pages), `A/pages/Login.tsx:49-52`.
- H20 **Revoked platform admin is never signed out** (interceptor ignores 403; refresh still succeeds). `A/lib/api-client.ts:45-59`.
- H21 **Plan "Assign" with the default empty selection silently unassigns the tenant's plan**; current plan never shown. `A/features/tenants/TenantDetailPage.tsx:76, 105-107, 331-347`.
- H22 **Suspend tenant, approve/deny access requests, bulk actions, template bundle edits, global flag toggles have no confirmation and no error UI**; partial bulk failure leaves a stale list. `A/features/tenants/TenantsPage.tsx:181-187`, `A/features/connector-requests/ConnectorRequestsPage.tsx:91-110`, `A/features/templates/TemplatesPage.tsx:281-347`.
- H23 **Non-admin login leaves a live tenant refresh cookie**; admin and web apps share one cookie on the API origin, so logging in to one rotates the other's session. `A/pages/Login.tsx:35-47`, `B/modules/auth/http.py:19-48`. Call `logout()` on the non-admin branch; separate cookie name/path for admin.
- H24 **Impersonation is a raw token hand-off**: no web-app consumer, no banner, no "end", target user is a free-text UUID. `A/features/tenants/TenantDetailPage.tsx:190-202, 735-767`.

### 2.3 Medium

- M1 Viewer read-only exemption is substring-based (`"/auth/" in path`, `endswith("/switch")`). A business-object type keyed `auth` yields `/business-objects/types/auth/records` → viewer writes allowed. `B/core/deps.py:81-96`. Anchor to exact routes.
- M2 Email enumeration via distinct 409s on signup and add-member (any Owner/Admin can probe platform-wide). `B/modules/auth/service.py:190, 233`, `B/modules/tenancy/router.py:224-229`.
- M3 Signup self-selects any `business_template_id` (even inactive) and inherits its `plan_id`; admin approval UI does not show template/plan. `B/modules/auth/service.py:210-215`.
- M4 No security headers (HSTS, nosniff, CSP, frame), `/docs`/`/redoc`/`/openapi.json` always on, no body size limit, no `TrustedHostMiddleware`. `B/main.py`.
- M5 Dev-default webhook verify tokens ship in source, accepted in prod, compared with `==`, and exposed to every tenant member via `ConnectorTypeOut.webhook_verify_token`. `B/modules/connectors/config.py:37, 83, 118`, `webhooks.py:187, 247, 290`.
- M6 Unauthenticated verify-token GETs decrypt every Instagram/Facebook credential; Razorpay without `?instance_id` HMACs against every instance. `B/modules/connectors/webhooks.py:206-277`, `razorpay/adapter.py:300-318`.
- M7 Upload reads whole body into memory before the 16 MB check; client `content_type` trusted (SVG/HTML stored XSS if bucket public); no MIME allow-list. `B/modules/connectors/router.py:296-323`.
- M8 OAuth callback redirect concatenates unencoded `error_description`/`str(exc)` into the SPA URL; `detail=str(exc)` forwards provider response bodies to the browser. `B/modules/connectors/router.py:173, 220-245, 315`.
- M9 Unbounded list endpoints across workflows, inbox, customers, orders, payments, tickets, media, clinic history, campaigns, connector events. Add `limit/offset` with `le=` caps.
- M10 No state machines: any Member sets any order/ticket status, rewrites `total_amount` after payment, creates `paid` orders; payment default currency `USD` vs Razorpay `INR`. `B/modules/orders/service.py:141-151`, `tickets/service.py:87-97`, `payments/schemas.py:25`.
- M11 Clinic queue: any member can POST `to_billing` and author `consultation_notes`; every doctor sees every doctor's notes; position counter is `max+1` without locking. `B/modules/clinic_queue/router.py:89-113`, `service.py:48-56, 130-136, 190-220`.
- M12 `simulate` executes real side effects against the draft (sends, orders, payment links). `B/modules/workflows/service.py:346-380`.
- M13 Pollers hold a connection and `FOR UPDATE` locks for the whole batch; no per-run wall-clock ceiling (500 steps × 60 s × 3 retries). `B/modules/workflows/engine/run_loop.py:62`, `nodes/http_request.py:41`.
- M14 `_expire_stale_waits` runs after a raw commit in the same session (RLS → 0 rows on passes where a delay also resumed). `B/modules/workflows/engine/outbox_poller.py:121-200`.
- M15 Appointment pollers load every record per tenant and filter in Python every pass. `appointment_reminder_poller.py`, `feedback_poller.py`, `business_objects/service.py:163-179`.
- M16 Tickets `POST /{id}/messages` trusts client `author_type` (Member can forge customer/AI entries). `B/modules/tickets/router.py:107`.
- M17 Grandfathering inconsistency: HTTP gates use `resolve_module_access`, `connect()` uses raw `get_connector_access_map`. `B/modules/connectors/service.py:231-281, 383-393`.
- M18 `users.sidebar-layout` has `UNIQUE(user_id)` but is RLS-scoped by tenant → switching business and saving → 500. `B/modules/users/service.py:35-72`, migration 0036.
- M19 Owner step-up not applied to `PUT /connectors/role-restrictions`, connect/disconnect, template apply — inconsistent with commit f8a5bbb's intent.
- M20 Audit log: unauthenticated probes of `/api/admin` not logged; `ip_address` is the proxy behind Vercel; request bodies not captured (impersonate rows lack `target_user_id`); `SuspendTenantRequest.reason` exists but unused; `audit_extra` can overwrite reserved keys. `B/modules/admin/audit.py:69-114`.
- M21 Web: any failed refresh (network/5xx) logs the user out; `/connectors/*/connect` pages reachable by Member/Viewer with live forms; clinic scheduling card editable by Member while profile needs owner step-up; optimistic `isGranted()` during loading fires 403s and a misleading "permissions changed" toast; 403 detail strings matched in English; restriction changes propagate only after a 403; `meetLink` rendered as `href` without scheme check.
- M22 Admin: uncommitted diff reads `business_template_id` and `override_reason`/`override_set_by` that the backend schemas do not return (dead UI); sub-queries swallow errors and render misleading empty states; no idle timeout or step-up for a 30-day admin session; dropdown menu items not keyboard operable.
- M23 Admin ≡ Owner in power everywhere (no Owner-only action exists); decide whether Owner alone can add Admins / change restrictions / transfer ownership.

### 2.4 Low / hardening
No `iss`/`aud`/`typ` JWT claims; `jti` has no denylist; `get_tenant_context` ignores `accepted_at`; admin gate per-route not router-level; weak password policy (`min_length=8`); login revokes every other session for the business; `extra_connector_type_keys` unbounded; add-member `email: str` not `EmailStr` with check-then-insert race; `?status=<bad>` → 500 on admin requests list; weekday/timezone validators missing on schedules; `flow.loop.max_iterations` unbounded; `WORKFLOW_LOOP_GUARD_MAX` read from raw env; LIKE wildcards unescaped in search; coupon `usage_limit` never enforced; `_workflow_out` N+1; `entitlement.key_access` treats unknown keys (`appointment`) as granted; media deletion orphans R2 objects and ignores in-use references; ticket `attachments` unvalidated; `.env.example` missing `CRON_SECRET`, `RUNTIME_DATABASE_URL`, all connector settings; `_rls_smoke_test` table never dropped; `vercel.json` lacks `maxDuration`/Python pin; Google Fonts loaded from third party with no CSP in both SPAs; `VITE_API_URL` has no fallback/validation; admin `.env` disagrees with `.env.example`; hand-written shared TS types with no generator; no ESLint, zero frontend tests, single 1.38 MB web bundle, no `React.lazy`; stale READMEs; `docs/adr` is empty although README references it.

---

## 3. Route permission matrix (summary)

Legend: `None` public · `U` any valid token · `T` tenant member (viewer GET-only) · `M(key)` module gate (implies `T`) · `R(O/A)` owner/admin · `SU` owner step-up · `PA` platform admin · `HMAC` signature · ⚠️ gap.

| Module | Routes | Gate | Member can write? | Gap |
|---|---|---|---|---|
| auth | signup/login/refresh/logout | None | – | no rate limit (H1); refresh ignores business status (H4) |
| auth | select-business, me, step-up | U | – | accepts step-up & impersonation tokens (C3, C4) |
| tenancy | /businesses/{id} PATCH, /members POST/GET/PATCH | R(O/A)+SU | no | no DELETE member / role change (H3); Admin can create Admin |
| tenancy | /businesses/{id}/switch | U | – | viewer-exempt by suffix (intended) |
| users | /users/me/sidebar-layout | T | yes | unique(user_id) vs RLS (M18) |
| business_templates | /{id}/apply | **T** | **yes** | ⚠️ C5 |
| business_objects | types/fields/records | T (+M(appointments) for `appointment`) | yes | `{key}=auth` viewer bypass (M1); clinic settings ungated (M21) |
| custom_fields | definitions, templates/apply | M(custom_fields) | yes | schema edits by Member (decide) |
| catalog | products/services/coupons/offers | M(key) (+limit on POST) | yes incl. DELETE | – |
| customers | CRUD, field-definitions | M(customers) | yes incl. DELETE | ⚠️ C6 cascade |
| orders / tickets | CRUD | M(key) | yes | no state machine (M10); `author_type` trusted (M16) |
| payments | GET/POST | M(payments) | **yes** | ⚠️ manual captured payments by Member (H6) |
| clinic_queue | all | M(clinic_queue)+doctor SU | yes | ⚠️ key not seeded (C10); notes writable by any member (M11) |
| kb | CRUD | M(kb) | yes | – |
| connectors | types, list | T | – | verify_token exposed (M5) |
| connectors | role-restrictions GET/PUT, connect, request-access, test, disconnect | R(O/A) | no | no owner SU (M19) |
| connectors | /{id}/media POST | **T** | **yes** | ⚠️ H7 |
| connectors | /{id}/events GET | **T** | – | ⚠️ raw payloads to all roles (H7) |
| connectors | oauth/callback | None (state) | – | error leakage (M8) |
| whatsapp | templates CRUD/sync | M(whatsapp) | yes | not under `communication` restriction (H7) |
| instagram | ice-breakers, media | M(instagram) | yes | same |
| webhooks | POST whatsapp/instagram/facebook/razorpay/telegram | HMAC **or none** | – | ⚠️ C1 |
| workflows | CRUD, publish, delete, simulate, schedules, components | M(workflows) | **yes** | ⚠️ H6, M12 |
| workflows | /internal/scheduled-tasks | CRON_SECRET **or open** | – | ⚠️ C2 |
| predefined_automations, broadcast_campaigns, inbox, media_library, quick_replies | all | M(communication) *(new in diff)* | **yes** | ⚠️ broadcasts by Member (H6, H9) |
| /api/admin/* (50 routes) | all | PA (claim + DB flag) + audit | – | no router-level gate (Low); impersonation (C3) |

Regenerate per-route detail with `grep -rn "@router\." backend/src/fusionflow/modules`.

---

## 4. What is done well (keep)

- RLS: centralized helper, `ENABLE` + `FORCE`, `USING` + `WITH CHECK`, `NULLIF` fail-safe, 100 % coverage of the 39 tenant-scoped models; `SET LOCAL` with UUID type guard; `commit_and_keep_tenant_context` used in every HTTP handler.
- Per-request DB re-verification of membership, role and `is_platform_admin`; viewer read-only enforced centrally and against the fresh DB role.
- Argon2id, timing-equalized login, opaque SHA-256 refresh tokens with family rotation and reuse detection, httpOnly/Secure/path-scoped cookie, explicit CORS origin list.
- Startup refuses dev-default `JWT_SECRET`/`ENCRYPTION_KEY` outside development.
- Fernet-encrypted connector credentials with key-version column; secrets never serialized or logged; OAuth state 256-bit, 10-min TTL, tenant-bound, single-use; fixed `redirect_uri`.
- HMAC verification uses `compare_digest` over the raw body where configured; webhook idempotency via `(tenant_id, dedupe_key)` + savepoint; outbox/schedule pollers use `FOR UPDATE SKIP LOCKED`.
- Templating is a regex dot-path lookup (no eval/Jinja); conditions are a fixed operator table; no `eval/exec/pickle/yaml.load/subprocess` in `src/`.
- Unscoped engine confined to tenant lookup; every `/{business_id}` route guards against path IDOR.
- The uncommitted role-restriction work is correct: Owner/Admin only, Member/Viewer targets only, FEATURE-only, applied after grandfathering, enforced server-side with the fresh DB role; revoke-impact flow in admin is the right UX pattern; `tsc --noEmit` passes in both SPAs.
- Both SPAs keep the access token in memory only, single-flight refresh, no `dangerouslySetInnerHTML`, no token logging.

---

## 5. Phased plan to production

### Phase 0 — Blockers (before any real tenant; ~1 week)
1. `validate_secrets_for_environment`: also require `CRON_SECRET`, `RUNTIME_DATABASE_URL` (≠ `DATABASE_URL`), and global webhook app secrets; make `app_secret` required in every webhook-bearing adapter; `_dispatch` 401s when unverified outside dev. (C1, C2, H5)
2. JWT `typ` claims for access / step_up / impersonation; decoders require them; `select-business`, `switch`, `refresh`, `step-up` reject impersonation tokens; refuse platform-admin impersonation targets; add `POST /admin/impersonation/{id}/end` and check `ended_at`. (C3, C4)
3. `require_role(OWNER)` + step-up on template apply (or move to admin only). (C5)
4. Customer FK `ondelete` → `RESTRICT`/`SET NULL`; soft delete; owner/admin on delete. (C6)
5. Poller hardening: per-row SAVEPOINT + attempts + dead-letter in outbox; claim-then-execute in schedule poller; `commit_and_keep_tenant_context` in reminder poller and `_expire_stale_waits`; `SKIP LOCKED`/advisory lock in feedback and reminder pollers; tenant-configurable reminder text/timezone. (C7–C9, M14)
6. Data migration adding the `clinic_queue` catalog row. (C10)
7. Admin: fix Deny-on-Cancel; add app-level `ErrorBoundary` + `getErrorMessage()` for 422 arrays. (C11, H19)
8. Lockfile (`uv lock` or pinned `requirements.txt`), pin Python 3.13, CI running ruff + pytest + `alembic upgrade head` against a low-privilege Postgres role. (H13)

### Phase 1 — Security hardening (~2 weeks)
1. Rate limiting (login, step-up, signup, refresh, webhooks, verify-token GETs, internal) using `CacheBackend.incr`; account lockout. (H1, M6)
2. Remove `refresh_token` from browser response bodies; require `X-Requested-With`/Origin on cookie-authenticated POSTs; separate admin cookie name/path. (H2, H23)
3. Team lifecycle: remove member, change role (Owner only, last-owner guard), self-service password change, password reset, email verification; revoke refresh tokens on role change/removal; Admin-creates-Admin → Owner only. (H3, M23)
4. Enforce `Business.status == ACTIVE` in `get_tenant_context` and `refresh()`. (H4)
5. Role tiering: `require_role(OWNER, ADMIN)` on workflow publish/delete/schedule, broadcast create/activate/delete, manual payments, customer/media delete, WhatsApp template sync/delete, Instagram settings; stack `communication` gate on whatsapp/instagram routers, `/connectors/{id}/media` and `/connectors/{id}/events` (redact payload). (H6, H7)
6. Redact secrets in run-step input/variables; retention job for `workflow_run_steps`; `dry_run` flag for simulate. (H8, M12)
7. SSRF: block `not is_global`, response byte cap, pinned-IP transport, idempotent-only retries; validate R2 `endpoint_url`; stub mode only in dev. (H10–H12)
8. Security headers middleware, disable docs outside dev, body size limit, `TrustedHostMiddleware`; `compare_digest` on verify tokens and cron secret; remove dev-default verify tokens from prod. (M4, M5)
9. Anchor viewer exemptions to exact routes; `EmailStr` + IntegrityError handling on add-member; generic responses to stop email enumeration; `is_active` + plan deferral on signup template. (M1–M3)
10. Upload: stream with cap, MIME allow-list/sniff, `Content-Disposition: attachment`. (M7)
11. OAuth callback: `urlencode` params, map exceptions to generic codes; stop `detail=str(exc)`. (M8)

### Phase 2 — Frontend robustness (~1–2 weeks, parallel with Phase 1)
Web: interceptor skips refresh for step-up/login 401s and clears step-up state; `RequireStepUp` expiry timer; wrap `/onboarding` in `RequireStepUp`; cross-tab refresh lock; `queryClient.clear()` + step-up clear on sign-out/switch; tenant id in query keys; `isError` state in `useModuleAccess`/`RequireModule`/sidebar; `RequireRole` wrapper for connect pages; `enabled` guards on dependent queries; scheme check on `meetLink`; `ErrorBoundary`; route-level `React.lazy`; ESLint; vitest for `api-client`, `RequireModule`, `RequireStepUp`.

Admin: 403 → sign out; `logout()` on non-admin login; plan card shows current plan, disabled when unchanged, confirm on unassign; confirmations + error UI + `onSettled` invalidation for suspend/approve/deny/bulk/template/flag toggles; expose `plan_id`, `business_template_id`, `override_reason`, `override_set_by`, `tenant_count` from backend schemas so the diff's UI stops being dead code; impersonation target as a `<select>` over memberships, show `expires_in`; idle timeout; keyboard-operable menus.

### Phase 3 — Production operations (~2 weeks)
Structured JSON logging with request ids; Sentry (or equivalent) in API + both SPAs; `/readyz` with DB check; alembic in CI and on deploy; `vercel.json` `maxDuration` + Python pin; complete `.env.example`; pagination with caps on every list; order/ticket/payment state machines and amount freeze after capture; opt-out/suppression list + per-tenant send quotas; media deletion checks references; `sidebar_layouts` unique constraint per `(tenant_id, user_id)`; audit log: capture bodies, `X-Forwarded-For`, unauthenticated probes, suspension reason; drop `_rls_smoke_test`; write the missing ADRs (auth model, RLS, module entitlement, role restrictions); test coverage for: viewer gate, CRON auth, webhook rejection per adapter, SSRF edge cases, poller poison rows, member lifecycle, cascades.

### Phase 4 — Product decisions on the permission model
- Define what distinguishes **Owner** from **Admin** (ownership transfer, adding Admins, billing/plan, role restrictions).
- Consider a third axis beyond role × module: capability flags such as `can_send`, `can_delete`, `can_publish`, `can_view_pii`, or per-user (not per-role) module restrictions.
- Decide whether Member may edit schema-level things (custom fields, object types, clinic scheduling) or whether those are Admin-grade settings.
- Design the end-to-end impersonation experience in the web app (banner, exit, audit attribution of tenant-side actions).
- Decide the compliance posture for outbound messaging (opt-out semantics per channel, quiet hours, template-only outside 24 h windows).

---

## 6. Notes on the uncommitted work

The in-progress changes (role-module restrictions, `communication` gating of inbox/broadcast/predefined/media/quick-replies, appointment gate in business_objects, runtime entitlement in the engine, revoke-impact flow, `schedule_poller` FAILED-status fix) are sound and should be committed after:
- adding `business_template_id`, `override_reason`, `override_set_by` to the admin `TenantDetailOut` / `TenantModuleAccessOut` schemas (the admin UI already reads them);
- stacking the `communication` gate on the WhatsApp/Instagram routers and the connector media/events routes so the new restriction has no holes;
- nesting `audit_extra` under a `details` key so handler-supplied keys cannot overwrite `status_code`/`query`.
