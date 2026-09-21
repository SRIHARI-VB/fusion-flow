import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  Blocks,
  Building2,
  CreditCard,
  FileText,
  Flag,
  Layers,
  LayoutTemplate,
  LogOut,
  Plug,
  Sparkles,
  Wallet,
  Workflow,
} from "lucide-react";
import {
  Avatar,
  AvatarFallback,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  ThemeToggle,
  cn,
} from "@fusion-flow/ui";
import { useAuthStore } from "../lib/auth-store";
import { logout } from "../lib/endpoints";

const navItems = [
  { label: "Tenants", path: "/tenants", icon: Building2 },
  { label: "Audit log", path: "/audit-log", icon: FileText },
  { label: "Feature flags", path: "/feature-flags", icon: Flag },
  { label: "Templates", path: "/templates", icon: LayoutTemplate },
  { label: "Workflow nodes", path: "/workflow-node-templates", icon: Workflow },
  { label: "Starter Templates", path: "/workflow-starter-templates", icon: Layers },
  { label: "Components", path: "/workflow-components", icon: Blocks },
  { label: "Plans", path: "/plans", icon: CreditCard },
  { label: "Connector requests", path: "/connector-requests", icon: Plug },
  { label: "Billing", path: "/billing", icon: Wallet },
];

export function AdminLayout() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clear = useAuthStore((s) => s.clear);
  const initials = (user?.email ?? "A D").split("@")[0].slice(0, 2).toUpperCase();

  async function handleSignOut() {
    try {
      await logout();
    } finally {
      clear();
      navigate("/login", { replace: true });
    }
  }

  // `h-screen overflow-hidden` (not `min-h-screen`) - see frontend/web's
  // AppLayout for why: without a hard viewport-height cap here, a tall page
  // grows this whole flex row past 100vh and the *entire page* (sidebar
  // included) scrolls instead of just `<main>`.
  return (
    <div className="flex h-screen overflow-hidden bg-background">
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

      <div className="flex h-screen flex-1 flex-col overflow-hidden">
        <header className="flex h-16 items-center justify-end gap-3 border-b border-border bg-card px-6">
          <ThemeToggle />
          <DropdownMenu>
            <DropdownMenuTrigger>
              <button aria-label="Account menu">
                <Avatar>
                  <AvatarFallback className="bg-accent-soft text-accent">{initials}</AvatarFallback>
                </Avatar>
              </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              <DropdownMenuItem onClick={() => void handleSignOut()}>
                <LogOut className="mr-2 h-4 w-4" />
                Sign out
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </header>
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
