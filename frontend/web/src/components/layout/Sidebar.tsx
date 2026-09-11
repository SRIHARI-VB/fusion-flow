import { NavLink, useNavigate } from "react-router-dom";
import { ChevronLeft, ChevronRight, ChevronsUpDown, LogOut, Sparkles } from "lucide-react";
import {
  Avatar,
  AvatarFallback,
  Badge,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  cn,
} from "@fusion-flow/ui";
import { navGroups } from "./nav-config";
import { useAuthStore } from "../../lib/auth-store";
import { useLayoutStore } from "../../lib/layout-store";
import { logout } from "../../lib/endpoints";
import { useModuleAccess } from "../../lib/useModuleAccess";

export function Sidebar() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const business = useAuthStore((s) => s.business);
  const clear = useAuthStore((s) => s.clear);
  const { map: moduleAccess } = useModuleAccess();
  const collapsed = useLayoutStore((s) => s.sidebarCollapsed);
  const toggleCollapsed = useLayoutStore((s) => s.toggleSidebarCollapsed);

  const initials = (user?.email ?? "F F")
    .split("@")[0]
    .slice(0, 2)
    .toUpperCase();

  async function handleSignOut() {
    try {
      await logout();
    } finally {
      // Clear local state and redirect regardless of whether the network
      // call succeeded - the httpOnly refresh cookie is revoked server-side
      // when it does, but a dead/unreachable API must never trap the user
      // in a "can't sign out" state.
      clear();
      navigate("/login", { replace: true });
    }
  }

  if (collapsed) {
    return (
      <aside className="hidden w-14 shrink-0 flex-col items-center border-r border-sidebar-border bg-sidebar py-4 md:flex">
        <button
          type="button"
          aria-label="Expand sidebar"
          title="Expand sidebar"
          className="mb-4 flex h-8 w-8 items-center justify-center rounded-md bg-accent text-accent-foreground hover:opacity-90"
          onClick={toggleCollapsed}
        >
          <ChevronRight className="h-4 w-4" />
        </button>

        <nav className="flex flex-1 flex-col items-center gap-1 overflow-y-auto">
          {navGroups.flatMap((group) =>
            group.items.filter((item) => !item.moduleKey || moduleAccess[item.moduleKey] === "granted"),
          ).map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              title={item.label}
              aria-label={item.label}
              className={({ isActive }) =>
                cn(
                  "flex h-9 w-9 items-center justify-center rounded-md transition-colors",
                  isActive ? "bg-sidebar-active text-accent" : "text-sidebar-foreground hover:bg-muted",
                )
              }
            >
              <item.icon className="h-4 w-4" />
            </NavLink>
          ))}
        </nav>

        <DropdownMenu>
          <DropdownMenuTrigger>
            <button
              className="flex h-9 w-9 items-center justify-center rounded-md border-t border-sidebar-border hover:bg-muted"
              title={user?.email ?? "guest@fusion-flow"}
              aria-label="Account menu"
            >
              <Avatar>
                <AvatarFallback className="bg-accent-soft text-accent">{initials}</AvatarFallback>
              </Avatar>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" side="top" className="w-56">
            <DropdownMenuItem onClick={() => void handleSignOut()}>
              <LogOut className="mr-2 h-4 w-4" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </aside>
    );
  }

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
        <button
          type="button"
          aria-label="Collapse sidebar"
          title="Collapse sidebar"
          className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          onClick={toggleCollapsed}
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {navGroups.map((group) => {
          const visibleItems = group.items.filter(
            (item) => !item.moduleKey || moduleAccess[item.moduleKey] === "granted",
          );
          if (visibleItems.length === 0) return null;
          return (
          <div key={group.label} className="mb-5">
            <div className="mb-2 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {group.label}
            </div>
            <div className="flex flex-col gap-0.5">
              {visibleItems.map((item) => (
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
          );
        })}
      </nav>

      <DropdownMenu>
        <DropdownMenuTrigger>
          <button className="flex w-full items-center gap-2 border-t border-sidebar-border px-4 py-3 text-left hover:bg-muted">
            <Avatar>
              <AvatarFallback className="bg-accent-soft text-accent">{initials}</AvatarFallback>
            </Avatar>
            <div className="flex flex-1 flex-col overflow-hidden">
              <span className="truncate text-sm font-medium text-sidebar-foreground">
                {user?.email ?? "guest@fusion-flow"}
              </span>
              {business?.plan_name && (
                <Badge variant="default" className="mt-0.5 w-fit">
                  {business.plan_name} Plan
                </Badge>
              )}
            </div>
            <ChevronsUpDown className="h-4 w-4 text-muted-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" side="top" className="w-56">
          <DropdownMenuItem onClick={() => void handleSignOut()}>
            <LogOut className="mr-2 h-4 w-4" />
            Sign out
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </aside>
  );
}
