import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import type { AuthTokens } from "@fusion-flow/ts-types";
import { getAuthState } from "./auth-store";
import { classifyForbiddenDetail, emitAccessEvent } from "./access-events";
import { getStepUpAuthState } from "./step-up-auth-store";

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL,
  withCredentials: true, // send the httpOnly refresh cookie on every request
});

apiClient.interceptors.request.use((config) => {
  const { accessToken } = getAuthState();
  if (accessToken) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  // Clinic-queue routes require this header for doctor-flagged callers
  // (see backend/src/fusionflow/modules/clinic_queue/router.py) - harmless
  // to attach whenever a valid step-up session exists, since every other
  // route simply ignores it.
  const { token: stepUpToken, isValid } = getStepUpAuthState();
  if (stepUpToken && isValid()) {
    config.headers["X-Step-Up-Token"] = stepUpToken;
  }
  return config;
});

declare module "axios" {
  export interface InternalAxiosRequestConfig {
    _retried?: boolean;
  }
}

let refreshPromise: Promise<string | null> | null = null;

/** Exchanges the httpOnly refresh cookie for a fresh access token (and,
 * via `setSession`, repopulates `user`/`business` in the store) - used
 * reactively below on any 401, and proactively by `RequireAuth` on a
 * fresh page load, when the in-memory store is empty by design but the
 * cookie may still be valid. Concurrent callers share one in-flight
 * request (`refreshPromise`) rather than each firing their own. */
export async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = apiClient
      .post<AuthTokens>("/api/v1/auth/refresh", {}, { _retried: true } as InternalAxiosRequestConfig)
      .then((res) => {
        getAuthState().setSession(res.data);
        return res.data.access_token;
      })
      .catch(() => {
        getAuthState().clear();
        return null;
      })
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig | undefined;
    if (error.response?.status === 401 && original && !original._retried) {
      original._retried = true;
      const newToken = await refreshAccessToken();
      if (newToken) {
        original.headers = original.headers ?? {};
        original.headers.Authorization = `Bearer ${newToken}`;
        return apiClient(original);
      }
    }
    if (error.response?.status === 403) {
      // Access changed mid-session (module revoked/restricted) or a Viewer
      // hit a write - tell the UI; never alters the rejection itself.
      const detail = (error.response.data as { detail?: unknown } | undefined)?.detail;
      const kind = classifyForbiddenDetail(detail);
      if (kind) emitAccessEvent(kind, detail as string);
    }
    return Promise.reject(error);
  },
);
