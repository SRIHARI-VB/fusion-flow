import { useConnectorInstances } from "../../features/connectors/hooks";
import type { NavGroup, NavItem } from "./nav-config";
import type { EffectiveNavGroup } from "./sidebar-layout";

/**
 * Shared visibility/gating logic - used by both `Sidebar.tsx` (what actually
 * renders) and the Customize Sidebar settings card (what a user is even
 * allowed to reorder/rename/archive). Kept in one place so the two can never
 * drift apart - e.g. the editor must never show a group/item the tenant
 * doesn't actually have access to, since there'd be nothing real to
 * customize and it would misleadingly suggest the tenant has a module they
 * don't.
 */

// Communication-channel connector types - "at least one connected" is what
// unlocks `requiresAnyChannelConnected` nav items (currently just
// Appointments; see nav-config.ts's doc comment on that field).
export const CHANNEL_CONNECTOR_KEYS = new Set(["whatsapp", "instagram", "telegram", "facebook"]);

export function useHasAnyChannelConnected(): boolean {
  const { data: connectorInstances } = useConnectorInstances();
  return (connectorInstances ?? []).some(
    (instance) => instance.state === "connected" && CHANNEL_CONNECTOR_KEYS.has(instance.connector_type_key),
  );
}

export function isItemVisible(
  item: NavItem,
  moduleAccess: Record<string, string>,
  hasAnyChannelConnected: boolean,
): boolean {
  if (item.moduleKey && moduleAccess[item.moduleKey] !== "granted") return false;
  if (item.requiresAnyChannelConnected && !hasAnyChannelConnected) return false;
  return true;
}

// Outer gate for an entire group (e.g. "Communication") - checked before any
// of its items are considered, independent of each item's own `moduleKey`.
// See the doc comment on `NavGroup.moduleKey` in nav-config.ts.
export function isGroupVisible(group: NavGroup, moduleAccess: Record<string, string>): boolean {
  if (group.moduleKey && moduleAccess[group.moduleKey] !== "granted") return false;
  return true;
}

// `EffectiveNavGroup` (from sidebar-layout.ts) doesn't carry forward the
// original `NavGroup.moduleKey` - it only knows `key`/`label`/`archived`/
// `items`. To keep applying the existing group-level entitlement gate, look
// the effective group's `key` back up against the built-in `navGroups` (via
// `navGroupsByKey`) to find its original `NavGroup` and read `.moduleKey`
// from there. A custom group (or any effective group whose `key` has no
// match, which shouldn't normally happen for built-ins) has no
// corresponding original group and therefore no group-level gate - it
// always passes this check.
export function isEffectiveGroupVisible(
  group: EffectiveNavGroup,
  navGroupsByKey: Map<string, NavGroup>,
  moduleAccess: Record<string, string>,
): boolean {
  const original = navGroupsByKey.get(group.key);
  return original ? isGroupVisible(original, moduleAccess) : true;
}
