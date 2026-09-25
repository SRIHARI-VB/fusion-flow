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
  /**
   * Hides the item entirely (in both the expanded and collapsed sidebar)
   * unless the tenant has at least one CONNECTED communication-channel
   * connector instance (whatsapp/instagram/telegram/facebook). This is on
   * top of - not instead of - the `moduleKey` gate. Appointments only
   * exists because a connected channel's bot created them; showing the
   * nav entry with zero channels connected would just lead to a
   * permanently-empty, confusing page.
   */
  requiresAnyChannelConnected?: boolean;
}

export interface NavGroup {
  label: string;
  /**
   * An OUTER gate checked before any item inside this group is considered
   * for visibility - matches a `connector_types.key` the same way
   * `NavItem.moduleKey` does, via `useModuleAccess()`. When set and not
   * "granted", the entire group (and everything inside it) is hidden,
   * regardless of any individual item's own `moduleKey`. This lets a whole
   * feature area (e.g. "Communication") be admin-togglable as a unit,
   * independent of which individual items/channels within it are
   * separately enabled - a tenant needs BOTH this group-level key AND an
   * item's own `moduleKey` granted to see that item.
   */
  moduleKey?: string;
  items: NavItem[];
}

export const navGroups: NavGroup[] = [
  {
    label: "Main Menu",
    items: [
      { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard, moduleKey: "dashboard" },
      { label: "Products", path: "/products", icon: Package, moduleKey: "products" },
      { label: "Services", path: "/services", icon: Wrench, moduleKey: "services" },
      { label: "Coupons", path: "/coupons", icon: Tag, moduleKey: "coupons" },
      { label: "Offers", path: "/offers", icon: Gift, moduleKey: "offers" },
    ],
  },
  {
    label: "Operations",
    items: [
      { label: "Customers", path: "/customers", icon: Users, moduleKey: "customers" },
      {
        label: "Appointments",
        path: "/appointments",
        icon: CalendarClock,
        moduleKey: "appointments",
        requiresAnyChannelConnected: true,
      },
      { label: "Orders", path: "/orders", icon: ShoppingCart, moduleKey: "orders" },
      { label: "Payments", path: "/payments", icon: CreditCard, moduleKey: "payments" },
      { label: "Tickets", path: "/tickets", icon: LifeBuoy, moduleKey: "tickets" },
      { label: "Knowledge Base", path: "/kb", icon: BookOpen, moduleKey: "kb" },
    ],
  },
  {
    label: "Communication",
    moduleKey: "communication",
    items: [
      { label: "WhatsApp", path: "/communication/whatsapp/automations", icon: MessageCircle, moduleKey: "whatsapp" },
      { label: "Instagram", path: "/communication/instagram/automations", icon: Instagram, moduleKey: "instagram" },
      { label: "Telegram", path: "/communication/telegram/automations", icon: Send, moduleKey: "telegram" },
      { label: "Facebook", path: "/communication/facebook/automations", icon: Facebook, moduleKey: "facebook" },
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
