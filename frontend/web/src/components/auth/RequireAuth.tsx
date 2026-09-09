import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuthStore } from "../../lib/auth-store";

/**
 * Guards authenticated routes. Only checks the in-memory access token — on a hard reload the
 * token is gone by design (never persisted), so a real app would attempt a silent refresh via
 * the httpOnly cookie before deciding to redirect. That refresh call needs a live backend, which
 * isn't available in this sandbox; the guard below is deliberately simple for that reason.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken);
  if (!accessToken) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
