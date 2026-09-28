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
  Settings,
  SlidersHorizontal,
  MessageCircle,
  Instagram,
  Inbox,
  MessageSquareText,
  Image,
  Megaphone,
  CalendarClock,
} from "lucide-react";

export interface NavItem {
  label: string;
  /**
   * Stable, permanent identifier for this item - unique across the WHOLE
   * config (not just within its group). A saved per-user sidebar
   * customization (reordering, moving between groups, archiving) references
   * items by this key, so once assigned it must never change, even if the
   * item's `label`/`path` later does. Deliberately independent of
   * `moduleKey`, which is a different concept (a connector-catalog key)
   * that could in principle be reused or changed.
   */
  key: string;
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
   * Stable, permanent identifier for this group - unique among groups. See
   * `NavItem.key` for why this must never change once assigned and why it's
   * independent of `moduleKey`.
   */
  key: string;
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
    key: "main-menu",
    label: "Main Menu",
    items: [
      { key: "dashboard", label: "Dashboard", path: "/dashboard", icon: LayoutDashboard, moduleKey: "dashboard" },
      { key: "products", label: "Products", path: "/products", icon: Package, moduleKey: "products" },
      { key: "services", label: "Services", path: "/services", icon: Wrench, moduleKey: "services" },
      { key: "coupons", label: "Coupons", path: "/coupons", icon: Tag, moduleKey: "coupons" },
      { key: "offers", label: "Offers", path: "/offers", icon: Gift, moduleKey: "offers" },
    ],
  },
  {
    key: "operations",
    label: "Operations",
    items: [
      { key: "customers", label: "Customers", path: "/customers", icon: Users, moduleKey: "customers" },
      {
        key: "appointments",
        label: "Appointments",
        path: "/appointments",
        icon: CalendarClock,
        moduleKey: "appointments",
        requiresAnyChannelConnected: true,
      },
      { key: "orders", label: "Orders", path: "/orders", icon: ShoppingCart, moduleKey: "orders" },
      { key: "payments", label: "Payments", path: "/payments", icon: CreditCard, moduleKey: "payments" },
      { key: "tickets", label: "Tickets", path: "/tickets", icon: LifeBuoy, moduleKey: "tickets" },
      { key: "knowledge-base", label: "Knowledge Base", path: "/kb", icon: BookOpen, moduleKey: "kb" },
    ],
  },
  {
    key: "communication",
    label: "Communication",
    moduleKey: "communication",
    items: [
      {
        key: "whatsapp",
        label: "WhatsApp",
        path: "/communication/whatsapp/automations",
        icon: MessageCircle,
        moduleKey: "whatsapp",
      },
      {
        key: "instagram",
        label: "Instagram",
        path: "/communication/instagram/automations",
        icon: Instagram,
        moduleKey: "instagram",
      },
      // Common items - channel-agnostic, sit directly under Communication
      // rather than nested in any one channel.
      { key: "inbox", label: "Inbox", path: "/communication/inbox", icon: Inbox },
      { key: "quick-replies", label: "Quick Replies", path: "/communication/quick-replies", icon: MessageSquareText },
      { key: "media-library", label: "Media Library", path: "/communication/media-library", icon: Image },
      {
        key: "broadcast-campaigns",
        label: "Broadcast Campaigns",
        path: "/communication/broadcasts",
        icon: Megaphone,
      },
    ],
  },
  {
    key: "management",
    label: "Management",
    items: [
      { key: "connectors", label: "Connectors", path: "/connectors", icon: Plug },
      { key: "workflows", label: "Workflows", path: "/workflows", icon: Workflow, moduleKey: "workflows" },
    ],
  },
  {
    key: "settings",
    label: "Settings",
    items: [
      {
        key: "custom-fields",
        label: "Custom Fields",
        path: "/settings/custom-fields",
        icon: SlidersHorizontal,
        moduleKey: "custom_fields",
      },
      { key: "settings", label: "Settings", path: "/settings", icon: Settings },
    ],
  },
];

export interface BreadcrumbMatch {
  groupLabel: string;
  itemLabel: string;
}

/**
 * Maps the current URL to its sidebar group + item label (e.g. "Main Menu"
 * + "Services"), so `Topbar` can show "Main Menu > Services" instead of
 * just "Services" - the group a page lives under is real navigational
 * context, not just decoration. A detail route (e.g. `/tickets/abc123`)
 * matches its list page's item (`/tickets`) via prefix, same convention
 * `Sidebar.tsx` already uses for auto-expanding a parent on a child route.
 * Picks the LONGEST matching path when more than one item's path is a
 * prefix (e.g. `/settings/custom-fields` over the bare `/settings`), so a
 * more specific item always wins over a shorter, coincidentally-matching
 * one. Returns `null` for any route with no sidebar entry at all (e.g.
 * `/select-business`), leaving the caller's own fallback to handle it.
 */
export function findBreadcrumbForPath(pathname: string): BreadcrumbMatch | null {
  let best: BreadcrumbMatch | null = null;
  let bestPathLength = -1;

  for (const group of navGroups) {
    for (const item of group.items) {
      // A parent-with-children (e.g. "WhatsApp") has no `path` of its own -
      // only its children are ever navigable, so only they can match.
      const candidates = item.children && item.children.length > 0 ? item.children : [item];
      for (const candidate of candidates) {
        if (!candidate.path) continue;
        const isMatch = pathname === candidate.path || pathname.startsWith(`${candidate.path}/`);
        if (isMatch && candidate.path.length > bestPathLength) {
          bestPathLength = candidate.path.length;
          best = { groupLabel: group.label, itemLabel: candidate.label };
        }
      }
    }
  }

  return best;
}
