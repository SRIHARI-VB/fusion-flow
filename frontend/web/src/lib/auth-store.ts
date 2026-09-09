import { create } from "zustand";
import type { AuthTokens, Business, DecodedAccessToken, User } from "@fusion-flow/ts-types";
import { decodeAccessToken } from "./jwt";

/**
 * In-memory-only auth store. The access token is NEVER persisted to localStorage/sessionStorage
 * — that is a hard security requirement from the architecture plan (XSS-exfiltrated tokens from
 * localStorage are a much larger blast radius than an in-memory value that disappears on reload).
 * The refresh token lives in an httpOnly cookie set by the backend and is never readable/settable
 * from JS at all. On a hard page reload, `accessToken` is gone and the app relies on the
 * axios response interceptor's refresh-on-401 flow (using the httpOnly cookie) to get a new one.
 */
interface AuthState {
  accessToken: string | null;
  claims: DecodedAccessToken | null;
  user: User | null;
  business: Business | null;
  setSession: (session: AuthTokens) => void;
  setAccessToken: (accessToken: string) => void;
  setBusiness: (business: Business) => void;
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  claims: null,
  user: null,
  business: null,
  setSession: (session) => {
    const claims = decodeAccessToken(session.access_token);
    // There is no singular `business` field on the response - resolve the
    // active one by matching the token's `tenant_id` claim against the
    // `businesses` list. `tenant_id` is null on a pre-tenant token
    // (requires_business_selection: true), which correctly resolves to
    // `undefined` here, i.e. no active business yet.
    const business = session.businesses.find((b) => b.id === claims.tenant_id);
    set({
      accessToken: session.access_token,
      claims,
      user: session.user,
      business: business ?? null,
    });
  },
  setAccessToken: (accessToken) =>
    set({ accessToken, claims: decodeAccessToken(accessToken) }),
  // Reflects an in-place business update (e.g. onboarding setting vertical /
  // marking onboarding complete) without minting new tokens - the business
  // profile fields aren't part of the JWT claims, just `AuthTokens.business`.
  setBusiness: (business) => set({ business }),
  clear: () => set({ accessToken: null, claims: null, user: null, business: null }),
}));

/** Non-hook accessor for use outside React (e.g. the axios interceptor). */
export function getAuthState() {
  return useAuthStore.getState();
}
