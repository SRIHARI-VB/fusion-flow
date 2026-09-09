import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuthStore } from "../lib/auth-store";

export function RequireAdmin({ children }: { children: ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const claims = useAuthStore((s) => s.claims);
  if (!accessToken || !claims?.platform_admin) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
