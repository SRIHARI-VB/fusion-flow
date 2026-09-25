import type { NavGroup, NavItem } from "./nav-config";

/**
 * Wire contract for `GET/PUT /api/v1/users/me/sidebar-layout` - matches the
 * backend's per-user sidebar-layout storage API exactly. Keep these types in
 * lockstep with the backend response/request shape; don't add fields here
 * speculatively.
 *
 * A layout is a SPARSE set of overrides on top of `navGroups` (see
 * `nav-config.ts`), not a full replacement - anything not mentioned here
 * keeps its default position/visibility. Groups/items are referenced by
 * their permanent `key` (built-in groups/items) or by a generated custom
 * group id (see `SidebarLayoutGroup.id` below).
 */
export interface SidebarLayoutGroup {
  /**
   * For a built-in group this is its `NavGroup.key`. For a custom
   * (user-created) group this is a generated id (e.g. a uuid) with no
   * corresponding entry in `navGroups`.
   */
  id: string;
  kind: "builtin" | "custom";
  /** Set (and equal to `id`) when `kind === "builtin"`; omitted for custom groups. */
  builtinKey?: string;
  /**
   * User-chosen display name. Always set for custom groups (their only
   * label). Optional for built-in groups - when present it overrides that
   * group's default `NavGroup.label` (a rename); when absent the built-in
   * group keeps its default label.
   */
  label?: string;
  order: number;
  archived: boolean;
}

export interface SidebarLayoutItem {
  /**
   * The group this item currently belongs to - references a
   * `SidebarLayoutGroup.id` from `groups` above, OR the `key` of a built-in
   * group the item was never moved out of. Can differ from the item's
   * original built-in group (including pointing into a custom group).
   */
  groupId: string;
  order: number;
  archived: boolean;
}

export interface SidebarLayout {
  groups: SidebarLayoutGroup[];
  /** Keyed by the item's permanent `NavItem.key`. */
  items: Record<string, SidebarLayoutItem>;
}

/** An effective (post-merge) nav item - still carries the original `NavItem`
 * so callers can keep running the existing `moduleKey` /
 * `requiresAnyChannelConnected` gating exactly as `Sidebar.tsx` does today;
 * this module has no opinion on that gating. */
export interface EffectiveNavItem {
  item: NavItem;
  archived: boolean;
}

/** An effective (post-merge) nav group - `key` is either a built-in
 * `NavGroup.key` or a custom group's generated id. */
export interface EffectiveNavGroup {
  key: string;
  label: string;
  archived: boolean;
  items: EffectiveNavItem[];
}

/**
 * Merges `navGroups` (the built-in, static nav tree) with a user's saved
 * `SidebarLayout` override into the flat, ordered list the sidebar and the
 * settings editor both render from.
 *
 * Pure data transformation - no React, no fetch, safe to unit test in
 * isolation. Does NOT apply `moduleKey`/`requiresAnyChannelConnected`
 * gating; that stays the caller's job (see `Sidebar.tsx`'s
 * `isItemVisible`/`isGroupVisible`), same as today.
 *
 * - `override === null`: base groups/items pass through unchanged, in their
 *   original order, everything unarchived - i.e. identical to just reading
 *   `navGroups` directly.
 * - `override` present: sparse - a base group/item not mentioned in
 *   `override.groups` / `override.items` defaults to
 *   `{ order: <its original index>, archived: false }`. A `kind: "custom"`
 *   group with no matching built-in becomes a new (initially empty) group
 *   using its `label`. An item's `groupId` can point it into any group
 *   (built-in or custom), not just its original one. Groups are sorted by
 *   `order`, then items within each group are sorted by `order`.
 */
export function computeEffectiveNav(
  baseGroups: NavGroup[],
  override: SidebarLayout | null,
): EffectiveNavGroup[] {
  if (!override) {
    return baseGroups.map((group) => ({
      key: group.key,
      label: group.label,
      archived: false,
      items: group.items.map((item) => ({ item, archived: false })),
    }));
  }

  const overrideGroupById = new Map(override.groups.map((g) => [g.id, g]));

  // Seed one bucket per eventual group: every built-in group (whether or
  // not it's mentioned in the override) plus every custom group the
  // override introduces.
  type OrderedItem = EffectiveNavItem & { order: number };
  type Bucket = {
    key: string;
    label: string;
    order: number;
    archived: boolean;
    items: OrderedItem[];
  };
  const buckets = new Map<string, Bucket>();

  baseGroups.forEach((group, index) => {
    const groupOverride = overrideGroupById.get(group.key);
    buckets.set(group.key, {
      key: group.key,
      label: groupOverride?.label ?? group.label,
      order: groupOverride?.order ?? index,
      archived: groupOverride?.archived ?? false,
      items: [],
    });
  });

  for (const groupOverride of override.groups) {
    if (groupOverride.kind === "custom" && !buckets.has(groupOverride.id)) {
      buckets.set(groupOverride.id, {
        key: groupOverride.id,
        label: groupOverride.label ?? "",
        order: groupOverride.order,
        archived: groupOverride.archived,
        items: [],
      });
    }
  }

  // Place every base item into its effective bucket (default: its original
  // built-in group, at its original index), honoring an override that
  // moves/reorders/archives it.
  baseGroups.forEach((group) => {
    group.items.forEach((item, index) => {
      const itemOverride = override.items[item.key];
      const targetGroupId = itemOverride?.groupId ?? group.key;
      const order = itemOverride?.order ?? index;
      const archived = itemOverride?.archived ?? false;

      let bucket = buckets.get(targetGroupId);
      if (!bucket) {
        // Override points at a group id that doesn't otherwise exist
        // (shouldn't normally happen if `override.groups` is well-formed) -
        // fall back to the item's original group rather than dropping it.
        bucket = buckets.get(group.key)!;
      }
      bucket.items.push({ item, archived, order });
    });
  });

  const effectiveGroups: EffectiveNavGroup[] = Array.from(buckets.values())
    .sort((a, b) => a.order - b.order)
    .map((bucket) => ({
      key: bucket.key,
      label: bucket.label,
      archived: bucket.archived,
      items: [...bucket.items]
        .sort((a, b) => a.order - b.order)
        .map(({ item, archived }) => ({ item, archived })),
    }));

  return effectiveGroups;
}
