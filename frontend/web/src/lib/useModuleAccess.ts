import { useConnectorTypes } from "../features/connectors/hooks";
import type { ConnectorAccessStatus } from "../features/connectors/types";
import { useAuthStore } from "./auth-store";

/**
 * Per-tenant access status keyed by catalog `key` (e.g. "products",
 * "tickets", "whatsapp") - built on the existing `useConnectorTypes()`
 * query (`GET /connectors/types`), which already returns `access_status`
 * generically for every catalog row, feature-kind or integration-kind,
 * with zero backend change needed. Reusing that hook (rather than a fresh
 * `useQuery`) guarantees this shares the same cache entry/key as the
 * Connectors grid, so requesting access from either surface invalidates
 * both.
 *
 * `isGranted(key)` is the convenience cross-module callers use to skip a
 * fetch / degrade a picker; while types are still loading it returns true
 * (optimistic) so pages don't flash a "unavailable" notice on first paint -
 * a real 403 is handled by the api-client interceptor anyway.
 */
export function useModuleAccess() {
  const { data, isLoading } = useConnectorTypes();
  const map: Record<string, ConnectorAccessStatus> = Object.fromEntries(
    (data ?? []).map((t) => [t.key, t.access_status]),
  );
  const isGranted = (key: string) => (isLoading ? true : map[key] === "granted");
  return { map, isLoading, isGranted };
}

/** Owner/Admin may connect/disconnect/test connectors and request module access. */
export function useCanManageAccess(): { role: string | undefined; canManage: boolean } {
  const role = useAuthStore((s) => s.business?.role);
  return { role, canManage: role === "owner" || role === "admin" };
}
