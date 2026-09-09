import { Bell, Search } from "lucide-react";
import { useLocation } from "react-router-dom";
import { Avatar, AvatarFallback, Button, Input, ThemeToggle } from "@fusion-flow/ui";
import { useAuthStore } from "../../lib/auth-store";

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

  const segment = location.pathname.split("/").filter(Boolean)[0] ?? "dashboard";

  return (
    <header className="flex h-16 items-center gap-4 border-b border-border bg-card px-6">
      <div className="flex items-center gap-1 text-sm">
        <span className="text-muted-foreground">Dashboard</span>
        <span className="text-muted-foreground">/</span>
        <span className="font-medium text-accent">{segmentLabel(segment)}</span>
      </div>

      <div className="ml-auto flex items-center gap-3">
        <div className="relative hidden sm:block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input placeholder="Search..." className="w-64 pl-9 pr-14" />
          <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-border bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">
            ⌘K
          </kbd>
        </div>

        <Button variant="ghost" size="icon" aria-label="Notifications">
          <Bell className="h-4 w-4" />
        </Button>

        <ThemeToggle />

        <Avatar>
          <AvatarFallback className="bg-accent-soft text-accent">{initials}</AvatarFallback>
        </Avatar>
      </div>
    </header>
  );
}
