/**
 * Hand-written shared types mirroring the phase-1 backend contract.
 * See README.md — this becomes OpenAPI-generated once more endpoints exist.
 */

export type MembershipRole = "owner" | "admin" | "member" | "viewer";

export type BusinessStatus = "pending_approval" | "active" | "suspended" | "denied";

export interface User {
  id: string;
  email: string;
  is_platform_admin: boolean;
  created_at: string;
}

/**
 * `created_at` and `role` are both optional because this same shape is used for two distinct
 * backend responses that each carry only one of them: `BusinessOut` (PATCH /businesses/{id}) has
 * `created_at`, no `role`; `BusinessMembershipOut` (GET /businesses/mine, and the `businesses`
 * list on every auth response) has `role`, no `created_at`. Every consumer in this app only
 * reads the fields common to both (id/name/slug/vertical/status/onboarding_completed_at).
 */
export interface Business {
  id: string;
  name: string;
  slug: string;
  vertical: string | null;
  status: BusinessStatus;
  messaging_paused: boolean;
  onboarding_completed_at: string | null;
  created_at?: string;
  role?: MembershipRole;
  /**
   * The tenant's plan name (e.g. "Pro"), if one is assigned - see
   * `Plan`/`Business.plan_id` in `modules.admin.models`/`modules.tenancy.models`.
   * Optional and nullable: not every response that returns a `Business`
   * populates it yet (see the "business templates / plans" task's report
   * for the exact `BusinessMembershipOut` change still needed to wire this
   * up end-to-end), and a tenant may simply have no plan assigned.
   */
  plan_name?: string | null;
}

export interface Membership {
  user_id: string;
  business_id: string;
  role: MembershipRole;
  invited_at: string;
  accepted_at: string | null;
}

/**
 * Decoded JWT access-token claims. `tenant_id`/`role` are null on a "pre-tenant" token
 * (multi-membership login before /select-business or /businesses/{id}/switch).
 * Platform-admin tokens carry `platform_admin: true` and omit `tenant_id`.
 */
export interface DecodedAccessToken {
  sub: string;
  tenant_id: string | null;
  role: MembershipRole | null;
  jti: string;
  platform_admin: boolean;
  iat: number;
  exp: number;
}

/**
 * Shape returned by POST /auth/login, /auth/signup, /auth/refresh,
 * /auth/select-business, /businesses/{id}/switch — mirrors the backend's
 * `TokenResponse` exactly. There is no singular `business` field: the
 * active business (if any) must be resolved client-side by matching the
 * decoded access token's `tenant_id` claim against this `businesses`
 * list (see auth-store.ts::setSession) - `requires_business_selection`
 * is true, and `tenant_id` is null, exactly when the caller has more
 * than one membership and hasn't picked one yet.
 */
export interface AuthTokens {
  access_token: string;
  token_type: string;
  expires_in: number;
  refresh_token?: string | null;
  requires_business_selection: boolean;
  user: User;
  businesses: Business[];
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  business_name: string;
  vertical?: string | null;
  business_template_id?: string | null;
  extra_connector_type_keys?: string[];
}

/**
 * Shape returned by POST /auth/signup now that self-serve signup requires
 * admin approval before any session is issued - no `access_token`/cookie,
 * just a confirmation that the application was recorded.
 */
export interface SignupResult {
  status: "pending_approval";
  business_id: string;
  business_name: string;
}
