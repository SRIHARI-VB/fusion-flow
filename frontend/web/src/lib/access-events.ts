/**
 * Tiny pub/sub so the axios response interceptor (plain module, no React
 * context) can tell the UI "your access changed" without importing the
 * QueryClient or the connectors hooks (which import api-client - a cycle).
 * `AccessNoticeToaster` (mounted in `AppLayout`) is the one subscriber.
 */
export type AccessEventKind = "module_access_changed" | "read_only";

type Listener = (kind: AccessEventKind, detail: string) => void;
const listeners = new Set<Listener>();

export function subscribeAccessEvents(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function emitAccessEvent(kind: AccessEventKind, detail: string): void {
  listeners.forEach((l) => l(kind, detail));
}

/** Exact `detail` strings the API uses on a 403 - see the backend's module/role gates. */
const MODULE_DETAILS = [
  "Your business does not have access to this module.",
  "Your role does not have access to this module. Ask an administrator.",
];
const READ_ONLY_DETAIL = "Viewers have read-only access.";

export function classifyForbiddenDetail(detail: unknown): AccessEventKind | null {
  if (typeof detail !== "string") return null;
  if (detail === READ_ONLY_DETAIL) return "read_only";
  if (MODULE_DETAILS.includes(detail) || detail.startsWith("Module '")) return "module_access_changed";
  return null;
}

/** Best-effort extraction of a FastAPI `detail` string from an axios error. */
export function getApiErrorDetail(error: unknown, fallback: string): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail;
  return typeof detail === "string" && detail ? detail : fallback;
}
