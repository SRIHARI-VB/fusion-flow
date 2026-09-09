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
  clear: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  claims: null,
  user: null,
  business: null,
  setSession: (session) =>
    set({
      accessToken: session.access_token,
      claims: decodeAccessToken(session.access_token),
      user: session.user,
      business: session.business,
    }),
  setAccessToken: (accessToken) =>
    set({ accessToken, claims: decodeAccessToken(accessToken) }),
  clear: () => set({ accessToken: null, claims: null, user: null, business: null }),
}));

/** Non-hook accessor for use outside React (e.g. the axios interceptor). */
export function getAuthState() {
  return useAuthStore.getState();
}
