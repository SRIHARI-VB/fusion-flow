import { create } from "zustand";
import type { AuthTokens, DecodedAccessToken, User } from "@fusion-flow/ts-types";
import { decodeAccessToken } from "./jwt";

/**
 * In-memory-only admin session state — same rationale as frontend/web: the access token must
 * never be persisted to localStorage/sessionStorage.
 */
interface AdminAuthState {
  accessToken: string | null;
  claims: DecodedAccessToken | null;
  user: User | null;
  setSession: (session: AuthTokens) => void;
  clear: () => void;
}

export const useAuthStore = create<AdminAuthState>((set) => ({
  accessToken: null,
  claims: null,
  user: null,
  setSession: (session) =>
    set({
      accessToken: session.access_token,
      claims: decodeAccessToken(session.access_token),
      user: session.user,
    }),
  clear: () => set({ accessToken: null, claims: null, user: null }),
}));

export function getAuthState() {
  return useAuthStore.getState();
}
