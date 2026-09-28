import { Menu } from "lucide-react";
import { useLocation } from "react-router-dom";
import { Avatar, AvatarFallback, Button, ThemeToggle } from "@fusion-flow/ui";
import { useAuthStore } from "../../lib/auth-store";
import { useLayoutStore } from "../../lib/layout-store";
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
  const user = useAuthStore((s) => s.user);
  const initials = (user?.email ?? "F F").split("@")[0].slice(0, 2).toUpperCase();
  const toggleMobileNav = useLayoutStore((s) => s.toggleMobileNavOpen);

  const segment = location.pathname.split("/").filter(Boolean)[0] ?? "dashboard";
  // A detail page (e.g. a specific ticket/customer/workflow) can set a
  // precise title via `usePageTitle` - falling back to the generic
  // section name (derived from the route slug) when it hasn't.
  const pageTitle = usePageTitle();

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

      <span className="text-sm font-medium text-foreground">{pageTitle ?? segmentLabel(segment)}</span>

      <div className="ml-auto flex items-center gap-3">
        <ThemeToggle />

        <Avatar>
          <AvatarFallback className="bg-accent-soft text-accent">{initials}</AvatarFallback>
        </Avatar>
      </div>
    </header>
  );
}
