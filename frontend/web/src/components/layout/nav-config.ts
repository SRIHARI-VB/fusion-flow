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
  MessageCircle,
  Instagram,
  Send,
  Facebook,
  Zap,
  Inbox,
  MessageSquareText,
  Image,
  Megaphone,
  CalendarClock,
} from "lucide-react";

export interface NavItem {
  label: string;
  /**
   * Omitted for a parent item that exists purely to hold `children` (e.g.
   * a channel name under "Communication") - it renders as an
   * expand/collapse toggle instead of a link. Every leaf item (no
   * `children`) must set this.
   */
  path?: string;
  icon: LucideIcon;
  /**
   * Matches a `connector_types.key` for a fixed feature module (e.g.
   * "products", "tickets") - when set, the item is hidden unless
   * `useModuleAccess()` resolves it to "granted". Omitted for ungated
   * items (Dashboard, Connectors, Settings).
   */
  moduleKey?: string;
  /**
   * One extra level of nesting - e.g. "WhatsApp" (parent, `moduleKey:
   * "whatsapp"`) expanding to reveal "Automations". Not recursive beyond
   * this single level; `Sidebar.tsx` only renders parent -> children, not
   * grandchildren.
   */
  children?: NavItem[];
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
      { label: "Appointments", path: "/appointments", icon: CalendarClock },
      { label: "Orders", path: "/orders", icon: ShoppingCart, moduleKey: "orders" },
      { label: "Payments", path: "/payments", icon: CreditCard, moduleKey: "payments" },
      { label: "Tickets", path: "/tickets", icon: LifeBuoy, moduleKey: "tickets" },
      { label: "Knowledge Base", path: "/kb", icon: BookOpen, moduleKey: "kb" },
    ],
  },
  {
    label: "Communication",
    items: [
      {
        label: "WhatsApp",
        icon: MessageCircle,
        moduleKey: "whatsapp",
        children: [
          { label: "Automations", path: "/communication/whatsapp/automations", icon: Zap },
        ],
      },
      {
        label: "Instagram",
        icon: Instagram,
        moduleKey: "instagram",
        children: [
          { label: "Automations", path: "/communication/instagram/automations", icon: Zap },
        ],
      },
      {
        label: "Telegram",
        icon: Send,
        moduleKey: "telegram",
        children: [
          { label: "Automations", path: "/communication/telegram/automations", icon: Zap },
        ],
      },
      {
        label: "Facebook",
        icon: Facebook,
        moduleKey: "facebook",
        children: [
          { label: "Automations", path: "/communication/facebook/automations", icon: Zap },
        ],
      },
      // Common items - channel-agnostic, sit directly under Communication
      // rather than nested in any one channel.
      { label: "Inbox", path: "/communication/inbox", icon: Inbox },
      { label: "Quick Replies", path: "/communication/quick-replies", icon: MessageSquareText },
      { label: "Media Library", path: "/communication/media-library", icon: Image },
      { label: "Broadcast Campaigns", path: "/communication/broadcasts", icon: Megaphone },
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
