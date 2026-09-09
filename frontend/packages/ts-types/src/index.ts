/**
 * Hand-written shared types mirroring the phase-1 backend contract.
 * See README.md — this becomes OpenAPI-generated once more endpoints exist.
 */

export type MembershipRole = "owner" | "admin" | "member" | "viewer";

export type BusinessStatus = "active" | "suspended" | "pending";

export interface User {
  id: string;
  email: string;
  is_platform_admin: boolean;
  created_at: string;
}

export interface Business {
  id: string;
  name: string;
  slug: string;
  vertical: string | null;
  status: BusinessStatus;
  created_at: string;
  onboarding_completed_at: string | null;
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

/** Shape returned by POST /auth/login, /auth/signup, /auth/refresh, /businesses/{id}/switch. */
export interface AuthTokens {
  access_token: string;
  user: User;
  business: Business | null;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface SignupRequest {
  email: string;
  password: string;
  business_name: string;
}
