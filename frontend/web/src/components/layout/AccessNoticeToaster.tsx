import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Info, X } from "lucide-react";
import { subscribeAccessEvents, type AccessEventKind } from "../../lib/access-events";
import { connectorKeys } from "../../features/connectors/hooks";

const MESSAGES: Record<AccessEventKind, { title: string; body: string }> = {
  module_access_changed: {
    title: "Your access to this module changed",
    body: "An administrator changed your permissions. Your menu has been refreshed - contact your admin if you think this is a mistake.",
  },
  read_only: {
    title: "You have read-only access",
    body: "Viewers can look but not change anything. Ask an Owner or Admin to upgrade your role.",
  },
};

/**
 * Minimal toast (the UI kit has none). Listens for 403s classified by the
 * api-client interceptor, refreshes `/connectors/types` so nav/RequireModule
 * reflect the new access, and shows each kind at most once per 30s so a page
 * firing several failing queries doesn't stack identical toasts.
 */
export function AccessNoticeToaster() {
  const queryClient = useQueryClient();
  const [active, setActive] = useState<AccessEventKind | null>(null);
  const lastShown = useRef<Partial<Record<AccessEventKind, number>>>({});

  useEffect(() => {
    return subscribeAccessEvents((kind) => {
      if (kind === "module_access_changed") {
        void queryClient.invalidateQueries({ queryKey: connectorKeys.types });
      }
      const now = Date.now();
      if (now - (lastShown.current[kind] ?? 0) < 30_000) return;
      lastShown.current[kind] = now;
      setActive(kind);
    });
  }, [queryClient]);

  useEffect(() => {
    if (!active) return;
    const t = setTimeout(() => setActive(null), 8_000);
    return () => clearTimeout(t);
  }, [active]);

  if (!active) return null;
  const message = MESSAGES[active];
  return (
    <div
      role="status"
      className="fixed bottom-4 right-4 z-50 flex w-80 items-start gap-3 rounded-md border border-border bg-card p-4 shadow-lg"
    >
      <Info className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
      <div className="flex-1">
        <p className="text-sm font-medium text-foreground">{message.title}</p>
        <p className="mt-1 text-xs text-muted-foreground">{message.body}</p>
      </div>
      <button type="button" aria-label="Dismiss" onClick={() => setActive(null)}>
        <X className="h-4 w-4 text-muted-foreground" />
      </button>
    </div>
  );
}
