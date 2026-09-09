import { useEffect, useState, type ReactNode } from "react";
import type { InternalAxiosRequestConfig } from "axios";
import { apiClient } from "../../lib/api-client";
import { getAuthState } from "../../lib/auth-store";
import type { AuthTokens } from "@fusion-flow/ts-types";

/**
 * Attempts one silent session restore on hard page load, before any route
 * (including `RequireAuth`) renders.
 *
 * The access token is intentionally never persisted (see auth-store.ts), so
 * a reload always starts with `accessToken: null` - without this, every
 * reload of an authenticated page looked exactly like a logged-out session
 * and bounced straight to /login, even though the httpOnly refresh cookie
 * was still valid the whole time. `POST /auth/refresh` reads that cookie
 * directly; if it 401s (no cookie / expired / revoked), we fall through to
 * the normal logged-out state and let `RequireAuth` redirect as usual.
 */
export function AuthBootstrap({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      if (!getAuthState().accessToken) {
        try {
          const { data } = await apiClient.post<AuthTokens>(
            "/api/v1/auth/refresh",
            {},
            // Marked _retried so the response interceptor never tries a second
            // refresh on top of this one if it itself 401s.
            { _retried: true } as InternalAxiosRequestConfig,
          );
          if (!cancelled) getAuthState().setSession(data);
        } catch {
          // No valid refresh cookie - stay logged out, RequireAuth handles the redirect.
        }
      }
      if (!cancelled) setReady(true);
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  // Deliberately renders nothing (not even a spinner) for what is normally a
  // sub-100ms same-origin request, to avoid a flash of empty layout before
  // the real page mounts.
  if (!ready) return null;
  return <>{children}</>;
}
