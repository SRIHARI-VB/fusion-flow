import { useMemo, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import {
  Archive,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  LogOut,
  Sparkles,
} from "lucide-react";
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
import { navGroups, type NavItem } from "./nav-config";
import { computeEffectiveNav } from "./sidebar-layout";
import { isEffectiveGroupVisible, isItemVisible, useHasAnyChannelConnected } from "./nav-visibility";
import { useAuthStore } from "../../lib/auth-store";
import { useLayoutStore } from "../../lib/layout-store";
import { useSidebarLayout } from "../../lib/useSidebarLayout";
import { logout } from "../../lib/endpoints";
import { useModuleAccess } from "../../lib/useModuleAccess";

// localStorage key for per-group expand/collapse UI state - deliberately NOT
// part of the persisted `SidebarLayout` (backend), since this is ephemeral
// per-browser convenience, not structural customization (reordering/
// archiving/custom groups), which lives server-side instead.
const COLLAPSED_GROUPS_STORAGE_KEY = "sidebar-collapsed-groups";

function readCollapsedGroups(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(COLLAPSED_GROUPS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    return parsed && typeof parsed === "object" ? (parsed as Record<string, boolean>) : {};
  } catch {
    return {};
  }
}

function writeCollapsedGroups(value: Record<string, boolean>) {
  try {
    localStorage.setItem(COLLAPSED_GROUPS_STORAGE_KEY, JSON.stringify(value));
  } catch {
    // Best-effort only (private browsing / storage quota) - collapse state
    // just won't survive a reload, which is harmless.
  }
}

export function Sidebar() {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((s) => s.user);
  const business = useAuthStore((s) => s.business);
  const clear = useAuthStore((s) => s.clear);
  const { map: moduleAccess } = useModuleAccess();
  const hasAnyChannelConnected = useHasAnyChannelConnected();
  const collapsed = useLayoutStore((s) => s.sidebarCollapsed);
  const toggleCollapsed = useLayoutStore((s) => s.toggleSidebarCollapsed);

  // The user's saved sidebar customization (reordering/archiving/custom
  // groups), merged on top of the built-in `navGroups` into the flat,
  // ordered list actually rendered below. `layout === null` (no saved
  // customization yet, or still loading) renders identically to the
  // built-in `navGroups`.
  const { layout } = useSidebarLayout();
  const effectiveGroups = useMemo(() => computeEffectiveNav(navGroups, layout), [layout]);
  const navGroupsByKey = useMemo(() => new Map(navGroups.map((group) => [group.key, group])), []);

  // Which parent-with-children items are expanded, keyed by label (unique
  // within a group, and this sidebar's nav tree is small enough that a
  // plain label key - rather than a synthetic id - is fine). A parent
  // whose current route matches one of its children auto-expands on
  // mount/navigation even if the set below doesn't mention it yet.
  const [manuallyToggled, setManuallyToggled] = useState<Record<string, boolean>>({});
  const autoExpanded = useMemo(() => {
    const labels = new Set<string>();
    for (const group of navGroups) {
      for (const item of group.items) {
        if (item.children?.some((child) => child.path && location.pathname.startsWith(child.path))) {
          labels.add(item.label);
        }
      }
    }
    return labels;
  }, [location.pathname]);

  function isExpanded(label: string): boolean {
    return manuallyToggled[label] ?? autoExpanded.has(label);
  }

  function toggleExpanded(label: string) {
    setManuallyToggled((prev) => ({ ...prev, [label]: !isExpanded(label) }));
  }

  // Per-group collapse/expand (expanded sidebar only) - purely a per-browser
  // UI convenience, persisted to localStorage rather than the backend
  // `SidebarLayout`. Defaults to expanded when a group has no stored
  // preference.
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>(readCollapsedGroups);

  function isGroupCollapsed(groupKey: string): boolean {
    return collapsedGroups[groupKey] ?? false;
  }

  function toggleGroupCollapsed(groupKey: string) {
    setCollapsedGroups((prev) => {
      const next = { ...prev, [groupKey]: !(prev[groupKey] ?? false) };
      writeCollapsedGroups(next);
      return next;
    });
  }

  // Whether the "Archive" entry is expanded - transient UI state, not
  // persisted (unlike per-group collapse above).
  const [archiveExpanded, setArchiveExpanded] = useState(false);

  // Everything archived, flattened: every item belonging to an archived
  // group, plus every individually-archived item inside a non-archived
  // group - each still gated by the same `isItemVisible` check as anything
  // else (an archived item a tenant no longer has access to shouldn't
  // render, even in the Archive list), and dropped entirely if its whole
  // group fails the group-level gate.
  const archivedNavItems = useMemo(() => {
    const result: NavItem[] = [];
    for (const group of effectiveGroups) {
      if (!isEffectiveGroupVisible(group, navGroupsByKey, moduleAccess)) continue;
      for (const effectiveItem of group.items) {
        if (!group.archived && !effectiveItem.archived) continue;
        if (isItemVisible(effectiveItem.item, moduleAccess, hasAnyChannelConnected)) {
          result.push(effectiveItem.item);
        }
      }
    }
    return result;
  }, [effectiveGroups, navGroupsByKey, moduleAccess, hasAnyChannelConnected]);

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
          {effectiveGroups
            // Collapsed icon-rail has no room for a nested archive concept
            // (or a per-group collapse toggle) - archived groups/items are
            // simply excluded here, not shown at all when collapsed.
            .filter((group) => !group.archived && isEffectiveGroupVisible(group, navGroupsByKey, moduleAccess))
            .flatMap((group) =>
              group.items
                .filter((effectiveItem) => !effectiveItem.archived)
                .map((effectiveItem) => effectiveItem.item)
                .filter((item) => isItemVisible(item, moduleAccess, hasAnyChannelConnected)),
            )
            // A parent-with-children (e.g. "WhatsApp") has no `path` of its
            // own and no room for an expand toggle in icon-only mode - it
            // links straight to its first child instead, using its own
            // (channel) icon so it's still visually distinguishable.
            .map((item) =>
              item.children && item.children.length > 0
                ? { path: item.children[0].path, icon: item.icon, label: item.label }
                : item,
            )
            .filter((item): item is NavItem & { path: string } => Boolean(item.path))
            .map((item) => (
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
        {effectiveGroups.map((group) => {
          if (group.archived) return null;
          if (!isEffectiveGroupVisible(group, navGroupsByKey, moduleAccess)) return null;
          const visibleItems = group.items
            .filter((effectiveItem) => !effectiveItem.archived)
            .map((effectiveItem) => effectiveItem.item)
            .filter((item) => isItemVisible(item, moduleAccess, hasAnyChannelConnected));
          if (visibleItems.length === 0) return null;
          const groupCollapsed = isGroupCollapsed(group.key);
          return (
          <div key={group.key} className="mb-5">
            <button
              type="button"
              onClick={() => toggleGroupCollapsed(group.key)}
              className="mb-2 flex w-full items-center gap-1 px-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground"
              aria-expanded={!groupCollapsed}
            >
              <ChevronDown
                className={cn("h-3 w-3 shrink-0 transition-transform", groupCollapsed && "-rotate-90")}
              />
              <span className="flex-1 text-left">{group.label}</span>
            </button>
            <div
              className={cn(
                "flex flex-col gap-0.5 overflow-hidden transition-[max-height,opacity] duration-200 ease-in-out",
                groupCollapsed ? "max-h-0 opacity-0" : "max-h-[1000px] opacity-100",
              )}
            >
              {visibleItems.map((item) =>
                item.children && item.children.length > 0 ? (
                  <div key={item.label}>
                    <button
                      type="button"
                      onClick={() => toggleExpanded(item.label)}
                      className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground transition-colors hover:bg-muted"
                      aria-expanded={isExpanded(item.label)}
                    >
                      <item.icon className="h-4 w-4" />
                      <span className="flex-1 text-left">{item.label}</span>
                      <ChevronDown
                        className={cn(
                          "h-3.5 w-3.5 shrink-0 transition-transform",
                          isExpanded(item.label) && "rotate-180",
                        )}
                      />
                    </button>
                    {isExpanded(item.label) && (
                      <div className="mt-0.5 flex flex-col gap-0.5 border-l border-sidebar-border pl-4">
                        {item.children
                          .filter((child) => isItemVisible(child, moduleAccess, hasAnyChannelConnected))
                          .map((child) => (
                            <NavLink
                              key={child.path}
                              to={child.path ?? "#"}
                              className={({ isActive }) =>
                                cn(
                                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                                  isActive
                                    ? "bg-sidebar-active text-accent"
                                    : "text-sidebar-foreground hover:bg-muted",
                                )
                              }
                            >
                              <child.icon className="h-4 w-4" />
                              {child.label}
                            </NavLink>
                          ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <NavLink
                    key={item.path}
                    to={item.path ?? "#"}
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
                ),
              )}
            </div>
          </div>
          );
        })}

        {archivedNavItems.length > 0 && (
          <div className="mt-1 border-t border-sidebar-border pt-3">
            <button
              type="button"
              onClick={() => setArchiveExpanded((prev) => !prev)}
              className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground transition-colors hover:bg-muted"
              aria-expanded={archiveExpanded}
            >
              <Archive className="h-4 w-4" />
              <span className="flex-1 text-left">Archive</span>
              <ChevronDown
                className={cn("h-3.5 w-3.5 shrink-0 transition-transform", archiveExpanded && "rotate-180")}
              />
            </button>
            <div
              className={cn(
                "flex flex-col gap-0.5 overflow-hidden transition-[max-height,opacity] duration-200 ease-in-out",
                archiveExpanded ? "mt-0.5 max-h-[1000px] opacity-100" : "max-h-0 opacity-0",
              )}
            >
              {archivedNavItems.map((item) => (
                <NavLink
                  key={item.key}
                  to={item.path ?? "#"}
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
          </div>
        )}
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
