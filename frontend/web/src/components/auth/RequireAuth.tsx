import { useEffect, useState, type ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { useAuthStore } from "../../lib/auth-store";
import { refreshAccessToken } from "../../lib/api-client";

/**
 * Guards authenticated routes. The in-memory access token (and everything
 * derived from it - `business`, `user`) is gone on a hard reload by design
 * (never persisted - see auth-store.ts). Rather than treating "no token
 * yet" as "not logged in" and redirecting immediately, this attempts one
 * silent refresh via the httpOnly refresh cookie first - the same
 * `refreshAccessToken` the axios interceptor already uses reactively on a
 * 401, just called proactively here before anything renders. Only redirects
 * to /login once that refresh has genuinely failed (no valid cookie/session
 * at all), not just because the in-memory store happens to be empty this
 * early in the page's life - this is what was causing Settings (and
 * anything else reading `business`/`user` straight from the store) to
 * render blank right after a reload, a timing race rather than guaranteed
 * behavior.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const [checkedSession, setCheckedSession] = useState(!!accessToken);

  useEffect(() => {
    if (accessToken) {
      setCheckedSession(true);
      return;
    }
    let cancelled = false;
    void refreshAccessToken().finally(() => {
      if (!cancelled) setCheckedSession(true);
    });
    return () => {
      cancelled = true;
    };
    // Only ever needs to run once per mount - re-running on every
    // `accessToken` change would re-trigger a refresh attempt right after
    // `clear()` (e.g. on sign-out), which should redirect, not retry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!checkedSession) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }
  // Re-reads the subscribed `accessToken` value, not a stale closure: the
  // store update from a successful `refreshAccessToken()` (inside
  // `setSession`) and this component's own re-render from `checkedSession`
  // flipping true land together, so this reflects whichever the refresh
  // actually produced.
  if (!accessToken) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
