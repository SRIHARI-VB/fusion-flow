import { useEffect, useState, type ReactNode } from "react";
import type { InternalAxiosRequestConfig } from "axios";
import { apiClient } from "../lib/api-client";
import { getAuthState } from "../lib/auth-store";
import type { AuthTokens } from "@fusion-flow/ts-types";

/**
 * Same rationale as frontend/web's AuthBootstrap: the access token is never
 * persisted, so a hard reload starts with `accessToken: null` and looked
 * exactly like a logged-out session even with a still-valid httpOnly
 * refresh cookie. Attempts one silent `/auth/refresh` before any route
 * (including `RequireAdmin`) renders.
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
            { _retried: true } as InternalAxiosRequestConfig,
          );
          if (!cancelled) getAuthState().setSession(data);
        } catch {
          // No valid refresh cookie - stay logged out, RequireAdmin handles the redirect.
        }
      }
      if (!cancelled) setReady(true);
    }

    void bootstrap();
    return () => {
      cancelled = true;
    };
  }, []);

  if (!ready) return null;
  return <>{children}</>;
}
