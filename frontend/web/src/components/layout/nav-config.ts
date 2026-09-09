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
} from "lucide-react";

export interface NavItem {
  label: string;
  path: string;
  icon: LucideIcon;
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
      { label: "Products", path: "/products", icon: Package },
      { label: "Services", path: "/services", icon: Wrench },
      { label: "Coupons", path: "/coupons", icon: Tag },
      { label: "Offers", path: "/offers", icon: Gift },
    ],
  },
  {
    label: "Customers",
    items: [
      { label: "Customers", path: "/customers", icon: Users },
      { label: "Orders", path: "/orders", icon: ShoppingCart },
      { label: "Payments", path: "/payments", icon: CreditCard },
      { label: "Tickets", path: "/tickets", icon: LifeBuoy },
      { label: "Knowledge Base", path: "/kb", icon: BookOpen },
    ],
  },
  {
    label: "Management",
    items: [
      { label: "Connectors", path: "/connectors", icon: Plug },
      { label: "Workflows", path: "/workflows", icon: Workflow },
      { label: "Support Agent", path: "/support-agent", icon: Bot },
    ],
  },
  {
    label: "Settings",
    items: [{ label: "Settings", path: "/settings", icon: Settings }],
  },
];
