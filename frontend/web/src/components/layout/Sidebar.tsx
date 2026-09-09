import { NavLink } from "react-router-dom";
import { ChevronsUpDown, Sparkles } from "lucide-react";
import { Avatar, AvatarFallback, Badge, cn } from "@fusion-flow/ui";
import { navGroups } from "./nav-config";
import { useAuthStore } from "../../lib/auth-store";

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const business = useAuthStore((s) => s.business);

  const initials = (user?.email ?? "F F")
    .split("@")[0]
    .slice(0, 2)
    .toUpperCase();

  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
      <div className="flex items-center gap-2 border-b border-sidebar-border px-4 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent text-accent-foreground">
          <Sparkles className="h-4 w-4" />
        </div>
        <div className="flex flex-1 flex-col overflow-hidden">
          <span className="truncate text-sm font-semibold text-sidebar-foreground">
            {business?.name ?? "fusion-flow"}
          </span>
          <span className="truncate text-xs text-muted-foreground">Workspace</span>
        </div>
        <ChevronsUpDown className="h-4 w-4 text-muted-foreground" />
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {navGroups.map((group) => (
          <div key={group.label} className="mb-5">
            <div className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {group.label}
            </div>
            <div className="flex flex-col gap-0.5">
              {group.items.map((item) => (
                <NavLink
                  key={item.path}
                  to={item.path}
                  className={({ isActive }) =>
                    cn(
                      "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-sidebar-active text-accent"
                        : "text-sidebar-foreground hover:bg-muted",
                    )
                  }
                >
                  <item.icon className="h-4 w-4" />
                  {item.label}
                </NavLink>
              ))}
            </div>
          </div>
        ))}
      </nav>

      <div className="flex items-center gap-2 border-t border-sidebar-border px-4 py-3">
        <Avatar>
          <AvatarFallback className="bg-accent-soft text-accent">{initials}</AvatarFallback>
        </Avatar>
        <div className="flex flex-1 flex-col overflow-hidden">
          <span className="truncate text-sm font-medium text-sidebar-foreground">
            {user?.email ?? "guest@fusion-flow"}
          </span>
          <Badge variant="default" className="mt-0.5 w-fit">
            Pro Plan
          </Badge>
        </div>
        <ChevronsUpDown className="h-4 w-4 text-muted-foreground" />
      </div>
    </aside>
  );
}
