import { NavLink, Outlet } from "react-router-dom";
import { Building2, FileText, Flag, LayoutTemplate, Sparkles, Wallet } from "lucide-react";
import { Avatar, AvatarFallback, ThemeToggle, cn } from "@fusion-flow/ui";
import { useAuthStore } from "../lib/auth-store";

const navItems = [
  { label: "Tenants", path: "/tenants", icon: Building2 },
  { label: "Audit log", path: "/audit-log", icon: FileText },
  { label: "Feature flags", path: "/feature-flags", icon: Flag },
  { label: "Templates", path: "/templates", icon: LayoutTemplate },
  { label: "Billing", path: "/billing", icon: Wallet },
];

export function AdminLayout() {
  const user = useAuthStore((s) => s.user);
  const initials = (user?.email ?? "A D").split("@")[0].slice(0, 2).toUpperCase();

  return (
    <div className="flex min-h-screen bg-background">
      <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
        <div className="flex items-center gap-2 border-b border-sidebar-border px-4 py-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent text-accent-foreground">
            <Sparkles className="h-4 w-4" />
          </div>
          <span className="text-sm font-semibold text-sidebar-foreground">fusion-flow admin</span>
        </div>
        <nav className="flex-1 px-3 py-4">
          <div className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Platform
          </div>
          <div className="flex flex-col gap-0.5">
            {navItems.map((item) => (
              <NavLink
                key={item.path}
                to={item.path}
                className={({ isActive }) =>
                  cn(
                    "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                    isActive ? "bg-sidebar-active text-accent" : "text-sidebar-foreground hover:bg-muted",
                  )
                }
              >
                <item.icon className="h-4 w-4" />
                {item.label}
              </NavLink>
            ))}
          </div>
        </nav>
      </aside>

      <div className="flex min-h-screen flex-1 flex-col">
        <header className="flex h-16 items-center justify-end gap-3 border-b border-border bg-card px-6">
          <ThemeToggle />
          <Avatar>
            <AvatarFallback className="bg-accent-soft text-accent">{initials}</AvatarFallback>
          </Avatar>
        </header>
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
