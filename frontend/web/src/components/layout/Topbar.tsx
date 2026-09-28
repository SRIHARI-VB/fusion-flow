import { Menu } from "lucide-react";
import { useLocation } from "react-router-dom";
import { Button, ThemeToggle } from "@fusion-flow/ui";
import { useLayoutStore } from "../../lib/layout-store";
import { findBreadcrumbForPath } from "./nav-config";
import { usePageTitle } from "./page-title";

function segmentLabel(path: string): string {
  if (!path) return "Dashboard";
  return path
    .split("-")
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
}

export function Topbar() {
  const location = useLocation();
  const toggleMobileNav = useLayoutStore((s) => s.toggleMobileNavOpen);

  const segment = location.pathname.split("/").filter(Boolean)[0] ?? "dashboard";
  // A detail page (e.g. a specific ticket/customer/workflow) can set a
  // precise title via `usePageTitle` - falling back to the generic
  // section name (derived from the route slug) when it hasn't.
  const pageTitle = usePageTitle();
  const breadcrumb = findBreadcrumbForPath(location.pathname);
  const currentLabel = pageTitle ?? breadcrumb?.itemLabel ?? segmentLabel(segment);
  // Skip the group prefix when it's identical to the item label (e.g.
  // "/settings" is both the "Settings" group and its own "Settings" item -
  // "Settings > Settings" would just look like a typo, not real context.
  const showGroupPrefix = breadcrumb && breadcrumb.groupLabel !== currentLabel;

  return (
    <header className="flex h-16 items-center gap-4 border-b border-border bg-card px-6">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        aria-label="Open navigation"
        onClick={toggleMobileNav}
      >
        <Menu className="h-5 w-5" />
      </Button>

      <div className="flex items-center gap-1 text-sm">
        {showGroupPrefix && (
          <>
            <span className="text-muted-foreground">{breadcrumb.groupLabel}</span>
            <span className="text-muted-foreground">/</span>
          </>
        )}
        <span className="font-medium text-foreground">{currentLabel}</span>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <ThemeToggle />
      </div>
    </header>
  );
}
