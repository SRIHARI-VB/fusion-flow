import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

/**
 * Lets a detail page (a specific ticket/customer/workflow, etc.) tell
 * `Topbar` its real title, instead of `Topbar` only ever being able to show
 * the generic section name derived from the route slug (e.g. "Tickets"
 * instead of "Ticket #4821 - Sarah Chen"). A page calls `useSetPageTitle`
 * in a `useEffect`; the title automatically reverts to the generic
 * fallback (`null`) when that page unmounts/navigates away, so a stale
 * title can never linger onto an unrelated page.
 */
interface PageTitleContextValue {
  title: string | null;
  setTitle: (title: string | null) => void;
}

const PageTitleContext = createContext<PageTitleContextValue | null>(null);

export function PageTitleProvider({ children }: { children: ReactNode }) {
  const [title, setTitle] = useState<string | null>(null);
  const value = useMemo(() => ({ title, setTitle }), [title]);
  return <PageTitleContext.Provider value={value}>{children}</PageTitleContext.Provider>;
}

function usePageTitleContext(): PageTitleContextValue {
  const ctx = useContext(PageTitleContext);
  if (!ctx) throw new Error("usePageTitleContext must be used within a PageTitleProvider");
  return ctx;
}

/** Read-only - `Topbar` uses this to render whatever the active page set. */
export function usePageTitle(): string | null {
  return usePageTitleContext().title;
}

/** A detail page calls this with its real title - reverts to the generic
 * fallback automatically on unmount, so navigating away always clears it. */
export function useSetPageTitle(title: string | null) {
  const { setTitle } = usePageTitleContext();
  useEffect(() => {
    setTitle(title);
    return () => setTitle(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [title]);
}
