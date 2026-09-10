import { useConnectorTypes } from "../features/connectors/hooks";
import type { ConnectorAccessStatus } from "../features/connectors/types";

/**
 * Per-tenant access status keyed by catalog `key` (e.g. "products",
 * "tickets", "whatsapp") - built on the existing `useConnectorTypes()`
 * query (`GET /connectors/types`), which already returns `access_status`
 * generically for every catalog row, feature-kind or integration-kind,
 * with zero backend change needed. Reusing that hook (rather than a fresh
 * `useQuery`) guarantees this shares the same cache entry/key as the
 * Connectors grid, so requesting access from either surface invalidates
 * both.
 */
export function useModuleAccess() {
  const { data, isLoading } = useConnectorTypes();
  const map: Record<string, ConnectorAccessStatus> = Object.fromEntries(
    (data ?? []).map((t) => [t.key, t.access_status]),
  );
  return { map, isLoading };
}
