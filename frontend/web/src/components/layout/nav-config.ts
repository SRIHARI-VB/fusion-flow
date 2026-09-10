import type { LucideIcon } from "lucide-react";
import {
  LayoutDashboard,
  Package,
  Wrench,
  Tag,
  Gift,
  Users,
  ShoppingCart,
  CreditCard,
  LifeBuoy,
  BookOpen,
  Plug,
  Workflow,
  Bot,
  Settings,
  SlidersHorizontal,
} from "lucide-react";

export interface NavItem {
  label: string;
  path: string;
  icon: LucideIcon;
  /**
   * Matches a `connector_types.key` for a fixed feature module (e.g.
   * "products", "tickets") - when set, the item is hidden unless
   * `useModuleAccess()` resolves it to "granted". Omitted for ungated
   * items (Dashboard, Connectors, Settings).
   */
  moduleKey?: string;
}

export interface NavGroup {
  label: string;
  items: NavItem[];
}

export const navGroups: NavGroup[] = [
  {
    label: "Main Menu",
    items: [
      { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
      { label: "Products", path: "/products", icon: Package, moduleKey: "products" },
      { label: "Services", path: "/services", icon: Wrench, moduleKey: "services" },
      { label: "Coupons", path: "/coupons", icon: Tag, moduleKey: "coupons" },
      { label: "Offers", path: "/offers", icon: Gift, moduleKey: "offers" },
    ],
  },
  {
    label: "Customers",
    items: [
      { label: "Customers", path: "/customers", icon: Users, moduleKey: "customers" },
      { label: "Orders", path: "/orders", icon: ShoppingCart, moduleKey: "orders" },
      { label: "Payments", path: "/payments", icon: CreditCard, moduleKey: "payments" },
      { label: "Tickets", path: "/tickets", icon: LifeBuoy, moduleKey: "tickets" },
      { label: "Knowledge Base", path: "/kb", icon: BookOpen, moduleKey: "kb" },
    ],
  },
  {
    label: "Management",
    items: [
      { label: "Connectors", path: "/connectors", icon: Plug },
      { label: "Workflows", path: "/workflows", icon: Workflow, moduleKey: "workflows" },
      { label: "Support Agent", path: "/support-agent", icon: Bot, moduleKey: "support_agent" },
    ],
  },
  {
    label: "Settings",
    items: [
      {
        label: "Custom Fields",
        path: "/settings/custom-fields",
        icon: SlidersHorizontal,
        moduleKey: "custom_fields",
      },
      { label: "Settings", path: "/settings", icon: Settings },
    ],
  },
];
