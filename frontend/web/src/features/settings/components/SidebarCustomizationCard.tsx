import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  useDroppable,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import {
  Archive,
  ArchiveRestore,
  ChevronDown,
  GripVertical,
  Pencil,
  Plus,
  Trash2,
} from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  cn,
} from "@fusion-flow/ui";
import { navGroups, type NavItem } from "../../../components/layout/nav-config";
import { computeEffectiveNav, type SidebarLayout } from "../../../components/layout/sidebar-layout";
import {
  isEffectiveGroupVisible,
  isItemVisible,
  useHasAnyChannelConnected,
} from "../../../components/layout/nav-visibility";
import { useModuleAccess } from "../../../lib/useModuleAccess";
import { useSaveSidebarLayout, useSidebarLayout } from "../../../lib/useSidebarLayout";
import { ConfirmDialog } from "./ConfirmDialog";

/**
 * A card on `/settings` (not a standalone page/nav destination - this is
 * personal preference, embedded alongside the other settings sections, the
 * same way `ClinicSchedulingCard` is) letting a user reorder/rename/archive
 * nav groups, move items between groups (including brand-new custom
 * groups), and archive individual items.
 *
 * Wave 1 (already merged) built the stable `key`s on `nav-config.ts`, the
 * pure `computeEffectiveNav` merge function, and the `useSidebarLayout`/
 * `useSaveSidebarLayout` hooks this card is built on top of.
 *
 * Only shows groups/items the tenant actually has access to right now
 * (same `isItemVisible`/`isEffectiveGroupVisible` gating `Sidebar.tsx`
 * itself uses) - there's nothing to customize about a module the tenant
 * can't see, and showing it here would misleadingly suggest they have it.
 *
 * All edits happen in local React state only — nothing hits the network
 * until "Save changes" is clicked. On save we always write out a FULLY
 * EXPLICIT `SidebarLayout` (every visible group, every visible item, real
 * `order`/`archived` values) rather than a sparse diff - simpler than
 * building diffing logic into the editor, and `computeEffectiveNav`'s
 * "missing entry keeps its default position" behavior only ever matters
 * for the zero-customization case anyway.
 */

interface EditableGroup {
  id: string;
  kind: "builtin" | "custom";
  builtinKey?: string;
  label: string;
  archived: boolean;
}

interface EditableItem {
  key: string;
  navItem: NavItem;
  archived: boolean;
}

interface EditorState {
  /** Group ids, in display order. */
  groupOrder: string[];
  groups: Record<string, EditableGroup>;
  /** Group id -> its items, in display order. Every item is always present
   * in exactly one group's list (no separate "unassigned" bucket). */
  itemsByGroup: Record<string, EditableItem[]>;
}

const BUILTIN_GROUP_KEYS = new Set(navGroups.map((g) => g.key));

// Every item's ORIGINAL built-in group - used only when a custom group
// containing it gets deleted, so the item can go back to where it started
// (see `deleteGroup` below). Built from the full, unfiltered `navGroups` -
// an item's original group is a static fact independent of current
// visibility.
const ITEM_ORIGINAL_GROUP: Record<string, string> = {};
for (const group of navGroups) {
  for (const item of group.items) {
    ITEM_ORIGINAL_GROUP[item.key] = group.key;
  }
}

const NAV_GROUPS_BY_KEY = new Map(navGroups.map((group) => [group.key, group]));

interface VisibilityContext {
  moduleAccess: Record<string, string>;
  hasAnyChannelConnected: boolean;
}

function buildInitialState(layout: SidebarLayout | null, visibility: VisibilityContext): EditorState {
  const effective = computeEffectiveNav(navGroups, layout);
  const groupOrder: string[] = [];
  const groups: Record<string, EditableGroup> = {};
  const itemsByGroup: Record<string, EditableItem[]> = {};

  for (const group of effective) {
    if (!isEffectiveGroupVisible(group, NAV_GROUPS_BY_KEY, visibility.moduleAccess)) continue;
    const visibleItems = group.items.filter((effectiveItem) =>
      isItemVisible(effectiveItem.item, visibility.moduleAccess, visibility.hasAnyChannelConnected),
    );
    // A custom group with nothing visible in it is still worth showing
    // (e.g. every item it held has since had access revoked) - but a
    // built-in group we've never customized with zero visible items would
    // just be dead weight, so skip those.
    const isBuiltin = BUILTIN_GROUP_KEYS.has(group.key);
    if (isBuiltin && visibleItems.length === 0) continue;

    groupOrder.push(group.key);
    groups[group.key] = {
      id: group.key,
      kind: isBuiltin ? "builtin" : "custom",
      builtinKey: isBuiltin ? group.key : undefined,
      label: group.label,
      archived: group.archived,
    };
    itemsByGroup[group.key] = visibleItems.map((effectiveItem) => ({
      key: effectiveItem.item.key,
      navItem: effectiveItem.item,
      archived: effectiveItem.archived,
    }));
  }

  return { groupOrder, groups, itemsByGroup };
}

function serializeState(state: EditorState): SidebarLayout {
  const groups = state.groupOrder.map((groupId, index) => {
    const group = state.groups[groupId];
    return {
      id: group.id,
      kind: group.kind,
      builtinKey: group.kind === "builtin" ? group.builtinKey : undefined,
      label: group.label,
      order: index,
      archived: group.archived,
    };
  });

  const items: SidebarLayout["items"] = {};
  for (const groupId of state.groupOrder) {
    const groupItems = state.itemsByGroup[groupId] ?? [];
    groupItems.forEach((item, index) => {
      items[item.key] = { groupId, order: index, archived: item.archived };
    });
  }

  return { groups, items };
}

function findItemContainer(state: EditorState, itemKey: string): string | undefined {
  return state.groupOrder.find((groupId) => (state.itemsByGroup[groupId] ?? []).some((it) => it.key === itemKey));
}

const CONTAINER_PREFIX = "container:";

function resolveOverContainer(state: EditorState, overId: string): string | undefined {
  if (overId.startsWith(CONTAINER_PREFIX)) {
    const groupId = overId.slice(CONTAINER_PREFIX.length);
    return state.groupOrder.includes(groupId) ? groupId : undefined;
  }
  const itemContainer = findItemContainer(state, overId);
  if (itemContainer) return itemContainer;
  return state.groupOrder.includes(overId) ? overId : undefined;
}

export function SidebarCustomizationCard() {
  const { layout, isLoading } = useSidebarLayout();
  const { map: moduleAccess } = useModuleAccess();
  const hasAnyChannelConnected = useHasAnyChannelConnected();
  const saveMutation = useSaveSidebarLayout();

  const [state, setState] = useState<EditorState | null>(null);
  const initializedRef = useRef(false);
  const lastSavedSerializedRef = useRef<string>("");

  useEffect(() => {
    if (!isLoading && !initializedRef.current) {
      const initial = buildInitialState(layout, { moduleAccess, hasAnyChannelConnected });
      setState(initial);
      lastSavedSerializedRef.current = JSON.stringify(serializeState(initial));
      initializedRef.current = true;
    }
    // Deliberately only re-runs when loading finishes (guarded by
    // `initializedRef`) - a later refetch (e.g. the invalidation this same
    // card triggers on save) must not clobber in-progress local edits.
  }, [isLoading, layout, moduleAccess, hasAnyChannelConnected]);

  // Tracked only to keep drag-start/drag-end symmetric; no `DragOverlay` is
  // rendered (each sortable row already moves itself via its own transform,
  // which is enough feedback here and avoids the extra portal/z-index setup
  // a floating overlay needs), so the value itself is never read.
  const [, setActiveId] = useState<string | null>(null);
  const [archivedExpanded, setArchivedExpanded] = useState(false);
  const [newGroupOpen, setNewGroupOpen] = useState(false);
  const [newGroupName, setNewGroupName] = useState("");
  const [pendingDeleteGroupId, setPendingDeleteGroupId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  const isDirty = useMemo(() => {
    if (!state) return false;
    return JSON.stringify(serializeState(state)) !== lastSavedSerializedRef.current;
  }, [state]);

  function updateGroup(groupId: string, patch: Partial<EditableGroup>) {
    setState((prev) => {
      if (!prev) return prev;
      const group = prev.groups[groupId];
      if (!group) return prev;
      return { ...prev, groups: { ...prev.groups, [groupId]: { ...group, ...patch } } };
    });
  }

  function toggleItemArchived(groupId: string, itemKey: string) {
    setState((prev) => {
      if (!prev) return prev;
      const items = prev.itemsByGroup[groupId] ?? [];
      const nextItems = items.map((item) => (item.key === itemKey ? { ...item, archived: !item.archived } : item));
      return { ...prev, itemsByGroup: { ...prev.itemsByGroup, [groupId]: nextItems } };
    });
  }

  function restoreItem(groupId: string, itemKey: string) {
    setState((prev) => {
      if (!prev) return prev;
      const items = prev.itemsByGroup[groupId] ?? [];
      const nextItems = items.map((item) => (item.key === itemKey ? { ...item, archived: false } : item));
      return { ...prev, itemsByGroup: { ...prev.itemsByGroup, [groupId]: nextItems } };
    });
  }

  function addGroup() {
    const label = newGroupName.trim();
    if (!label) return;
    const id = crypto.randomUUID();
    setState((prev) => {
      if (!prev) return prev;
      return {
        groupOrder: [...prev.groupOrder, id],
        groups: { ...prev.groups, [id]: { id, kind: "custom", label, archived: false } },
        itemsByGroup: { ...prev.itemsByGroup, [id]: [] },
      };
    });
    setNewGroupName("");
    setNewGroupOpen(false);
  }

  function deleteGroup(groupId: string) {
    setState((prev) => {
      if (!prev) return prev;
      const removedItems = prev.itemsByGroup[groupId] ?? [];
      const nextGroupOrder = prev.groupOrder.filter((id) => id !== groupId);
      const nextGroups = { ...prev.groups };
      delete nextGroups[groupId];
      const nextItemsByGroup = { ...prev.itemsByGroup };
      delete nextItemsByGroup[groupId];

      // Each removed item goes back to its ORIGINAL built-in group (never a
      // custom one, since items only ever originate from `navGroups`) -
      // equivalent to dropping its override entry entirely, just reflected
      // immediately instead of only after a reload. If that original group
      // isn't currently visible in the editor (e.g. access was revoked),
      // the item is simply dropped from view here - it's still correctly
      // unassigned in the saved layout and will reappear in its original
      // group once/if that group becomes visible again.
      for (const item of removedItems) {
        const originalGroupId = ITEM_ORIGINAL_GROUP[item.key];
        if (originalGroupId && nextItemsByGroup[originalGroupId]) {
          nextItemsByGroup[originalGroupId] = [...nextItemsByGroup[originalGroupId], item];
        }
      }

      return { groupOrder: nextGroupOrder, groups: nextGroups, itemsByGroup: nextItemsByGroup };
    });
    setPendingDeleteGroupId(null);
  }

  function handleDragStart(event: DragStartEvent) {
    setActiveId(String(event.active.id));
  }

  function handleDragOver(event: DragOverEvent) {
    const { active, over } = event;
    if (!over) return;
    const activeIdStr = String(active.id);
    const overIdStr = String(over.id);
    if (activeIdStr === overIdStr) return;

    setState((prev) => {
      if (!prev) return prev;
      if (prev.groupOrder.includes(activeIdStr)) return prev; // group drags: onDragEnd only

      const activeContainer = findItemContainer(prev, activeIdStr);
      if (!activeContainer) return prev;
      const overContainer = resolveOverContainer(prev, overIdStr);
      if (!overContainer || overContainer === activeContainer) return prev;

      const activeItems = prev.itemsByGroup[activeContainer] ?? [];
      const activeIndex = activeItems.findIndex((it) => it.key === activeIdStr);
      if (activeIndex === -1) return prev;
      const movedItem = activeItems[activeIndex];
      const nextActiveItems = activeItems.filter((it) => it.key !== activeIdStr);

      const overItems = prev.itemsByGroup[overContainer] ?? [];
      const overIndex = overItems.findIndex((it) => it.key === overIdStr);
      const insertAt = overIndex >= 0 ? overIndex : overItems.length;
      const nextOverItems = [...overItems.slice(0, insertAt), movedItem, ...overItems.slice(insertAt)];

      return {
        ...prev,
        itemsByGroup: {
          ...prev.itemsByGroup,
          [activeContainer]: nextActiveItems,
          [overContainer]: nextOverItems,
        },
      };
    });
  }

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    setActiveId(null);
    if (!over) return;
    const activeIdStr = String(active.id);
    const overIdStr = String(over.id);

    setState((prev) => {
      if (!prev) return prev;

      if (prev.groupOrder.includes(activeIdStr)) {
        if (activeIdStr === overIdStr || !prev.groupOrder.includes(overIdStr)) return prev;
        const oldIndex = prev.groupOrder.indexOf(activeIdStr);
        const newIndex = prev.groupOrder.indexOf(overIdStr);
        return { ...prev, groupOrder: arrayMove(prev.groupOrder, oldIndex, newIndex) };
      }

      const container = findItemContainer(prev, activeIdStr);
      if (!container) return prev;
      const items = prev.itemsByGroup[container] ?? [];
      const oldIndex = items.findIndex((it) => it.key === activeIdStr);
      const overIndex = items.findIndex((it) => it.key === overIdStr);
      const newIndex = overIndex === -1 ? oldIndex : overIndex;
      if (oldIndex === -1 || oldIndex === newIndex) return prev;
      return { ...prev, itemsByGroup: { ...prev.itemsByGroup, [container]: arrayMove(items, oldIndex, newIndex) } };
    });
  }

  function handleSave() {
    if (!state) return;
    const toSave = serializeState(state);
    const serialized = JSON.stringify(toSave);
    saveMutation.mutate(toSave, {
      onSuccess: () => {
        lastSavedSerializedRef.current = serialized;
      },
    });
  }

  const archivedGroups = state ? state.groupOrder.map((id) => state.groups[id]).filter((g) => g.archived) : [];
  const archivedItems = state
    ? state.groupOrder.flatMap((groupId) =>
        (state.itemsByGroup[groupId] ?? [])
          .filter((item) => item.archived)
          .map((item) => ({ groupId, item })),
      )
    : [];
  const archivedCount = archivedGroups.length + archivedItems.length;

  const pendingDeleteGroup = pendingDeleteGroupId && state ? state.groups[pendingDeleteGroupId] : null;
  const pendingDeleteItemCount =
    pendingDeleteGroupId && state ? (state.itemsByGroup[pendingDeleteGroupId] ?? []).length : 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Customize sidebar</CardTitle>
        <CardDescription>
          Reorder groups and items, rename or archive groups, move items between groups, or create
          your own groups. This is personal — it only changes what you see. Only shows what you
          currently have access to.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        {isLoading || !state ? (
          <p className="text-sm text-muted-foreground">Loading...</p>
        ) : (
          <>
            <DndContext
              sensors={sensors}
              collisionDetection={closestCenter}
              onDragStart={handleDragStart}
              onDragOver={handleDragOver}
              onDragEnd={handleDragEnd}
            >
              <SortableContext items={state.groupOrder} strategy={verticalListSortingStrategy}>
                <div className="flex flex-col gap-4">
                  {state.groupOrder.map((groupId) => (
                    <GroupCard
                      key={groupId}
                      group={state.groups[groupId]}
                      items={state.itemsByGroup[groupId] ?? []}
                      onRename={(label) => updateGroup(groupId, { label })}
                      onArchiveToggle={() => updateGroup(groupId, { archived: !state.groups[groupId].archived })}
                      onDelete={() => setPendingDeleteGroupId(groupId)}
                      onItemArchiveToggle={(itemKey) => toggleItemArchived(groupId, itemKey)}
                    />
                  ))}
                  {state.groupOrder.length === 0 && (
                    <p className="text-sm text-muted-foreground">
                      Nothing to customize yet — you don't have access to any nav groups.
                    </p>
                  )}
                </div>
              </SortableContext>
            </DndContext>

            <div>
              {newGroupOpen ? (
                <div className="flex items-center gap-2">
                  <Input
                    autoFocus
                    placeholder="Group name"
                    value={newGroupName}
                    onChange={(e) => setNewGroupName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") addGroup();
                      if (e.key === "Escape") {
                        setNewGroupOpen(false);
                        setNewGroupName("");
                      }
                    }}
                    className="max-w-xs"
                  />
                  <Button type="button" size="sm" onClick={addGroup}>
                    Create
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setNewGroupOpen(false);
                      setNewGroupName("");
                    }}
                  >
                    Cancel
                  </Button>
                </div>
              ) : (
                <Button type="button" variant="outline" onClick={() => setNewGroupOpen(true)}>
                  <Plus className="mr-1 h-4 w-4" />
                  New Group
                </Button>
              )}
            </div>

            {/* Archived section */}
            <div className="border-t border-border pt-4">
              <button
                type="button"
                onClick={() => setArchivedExpanded((prev) => !prev)}
                className="flex w-full items-center gap-2 text-sm font-semibold text-foreground"
                aria-expanded={archivedExpanded}
              >
                <ChevronDown className={cn("h-4 w-4 transition-transform", archivedExpanded && "-rotate-180")} />
                Archived ({archivedCount})
              </button>
              {archivedExpanded && (
                <div className="mt-3 flex flex-col gap-2">
                  {archivedCount === 0 && <p className="text-sm text-muted-foreground">Nothing archived.</p>}
                  {archivedGroups.map((group) => (
                    <div
                      key={group.id}
                      className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2"
                    >
                      <span className="text-sm text-foreground">
                        Group: <span className="font-medium">{group.label}</span>
                      </span>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => updateGroup(group.id, { archived: false })}
                      >
                        <ArchiveRestore className="mr-1 h-3.5 w-3.5" /> Restore
                      </Button>
                    </div>
                  ))}
                  {archivedItems.map(({ groupId, item }) => (
                    <div
                      key={item.key}
                      className="flex items-center justify-between rounded-md border border-border bg-card px-3 py-2"
                    >
                      <span className="flex items-center gap-2 text-sm text-foreground">
                        <item.navItem.icon className="h-4 w-4 text-muted-foreground" />
                        {item.navItem.label}
                        <span className="text-xs text-muted-foreground">
                          in {state.groups[groupId]?.label ?? groupId}
                        </span>
                      </span>
                      <Button type="button" variant="outline" size="sm" onClick={() => restoreItem(groupId, item.key)}>
                        <ArchiveRestore className="mr-1 h-3.5 w-3.5" /> Restore
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Save */}
            <div className="flex items-center gap-3 border-t border-border pt-4">
              <Button type="button" onClick={handleSave} disabled={saveMutation.isPending || !isDirty}>
                {saveMutation.isPending ? "Saving..." : "Save changes"}
              </Button>
              {isDirty && !saveMutation.isPending && (
                <span className="text-xs text-muted-foreground">Unsaved changes</span>
              )}
              {saveMutation.isError && (
                <span className="text-sm text-destructive">Could not save. Please try again.</span>
              )}
              {saveMutation.isSuccess && !saveMutation.isPending && !isDirty && (
                <span className="text-sm text-success">Saved.</span>
              )}
            </div>
          </>
        )}
      </CardContent>

      <ConfirmDialog
        open={pendingDeleteGroupId !== null}
        title={`Delete "${pendingDeleteGroup?.label ?? ""}"?`}
        description={`This will return ${pendingDeleteItemCount} item(s) to their default group. Continue?`}
        confirmLabel="Delete group"
        destructive
        onConfirm={() => pendingDeleteGroupId && deleteGroup(pendingDeleteGroupId)}
        onCancel={() => setPendingDeleteGroupId(null)}
      />
    </Card>
  );
}

interface GroupCardProps {
  group: EditableGroup;
  items: EditableItem[];
  onRename: (label: string) => void;
  onArchiveToggle: () => void;
  onDelete: () => void;
  onItemArchiveToggle: (itemKey: string) => void;
}

function GroupCard({ group, items, onRename, onArchiveToggle, onDelete, onItemArchiveToggle }: GroupCardProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: group.id });
  const { setNodeRef: setDroppableRef } = useDroppable({ id: `${CONTAINER_PREFIX}${group.id}` });
  const [editing, setEditing] = useState(false);
  const [labelDraft, setLabelDraft] = useState(group.label);

  const style: CSSProperties = {
    transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
    transition: transition ?? undefined,
    opacity: isDragging ? 0.6 : 1,
  };

  function commitRename() {
    const trimmed = labelDraft.trim();
    if (trimmed && trimmed !== group.label) onRename(trimmed);
    setLabelDraft(trimmed || group.label);
    setEditing(false);
  }

  return (
    <Card ref={setNodeRef} style={style} className={cn(group.archived && "opacity-60")}>
      <CardHeader className="flex-row items-center gap-2 space-y-0 p-4">
        <button
          type="button"
          className="cursor-grab touch-none text-muted-foreground hover:text-foreground active:cursor-grabbing"
          aria-label={`Reorder ${group.label} group`}
          {...attributes}
          {...listeners}
        >
          <GripVertical className="h-4 w-4" />
        </button>

        {editing ? (
          <Input
            autoFocus
            value={labelDraft}
            onChange={(e) => setLabelDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename();
              if (e.key === "Escape") {
                setLabelDraft(group.label);
                setEditing(false);
              }
            }}
            className="h-8 max-w-xs"
          />
        ) : (
          <CardTitle className="flex-1 truncate text-base">{group.label}</CardTitle>
        )}

        {!editing && (
          <button
            type="button"
            aria-label={`Rename ${group.label}`}
            className="text-muted-foreground hover:text-foreground"
            onClick={() => {
              setLabelDraft(group.label);
              setEditing(true);
            }}
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}

        {group.kind === "custom" && <Badge variant="outline">Custom</Badge>}
        {group.archived && <Badge variant="secondary">Archived</Badge>}

        <div className="ml-auto flex items-center gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onArchiveToggle}>
            {group.archived ? (
              <>
                <ArchiveRestore className="mr-1 h-3.5 w-3.5" /> Unarchive
              </>
            ) : (
              <>
                <Archive className="mr-1 h-3.5 w-3.5" /> Archive
              </>
            )}
          </Button>
          {group.kind === "custom" && (
            <Button type="button" variant="destructive" size="sm" onClick={onDelete}>
              <Trash2 className="mr-1 h-3.5 w-3.5" />
              Delete
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="p-4 pt-0">
        <div
          ref={setDroppableRef}
          className="flex min-h-[3.5rem] flex-col gap-2 rounded-md border border-dashed border-border p-2"
        >
          <SortableContext items={items.map((item) => item.key)} strategy={verticalListSortingStrategy}>
            {items.length === 0 && <p className="py-2 text-center text-xs text-muted-foreground">Drop items here</p>}
            {items.map((item) => (
              <ItemRow key={item.key} item={item} onArchiveToggle={() => onItemArchiveToggle(item.key)} />
            ))}
          </SortableContext>
        </div>
      </CardContent>
    </Card>
  );
}

interface ItemRowProps {
  item: EditableItem;
  onArchiveToggle: () => void;
}

function ItemRow({ item, onArchiveToggle }: ItemRowProps) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({ id: item.key });
  const style: CSSProperties = {
    transform: transform ? `translate3d(${transform.x}px, ${transform.y}px, 0)` : undefined,
    transition: transition ?? undefined,
    opacity: isDragging ? 0.5 : 1,
  };
  const Icon = item.navItem.icon;

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={cn(
        "flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2",
        item.archived && "opacity-60",
      )}
    >
      <button
        type="button"
        className="cursor-grab touch-none text-muted-foreground hover:text-foreground active:cursor-grabbing"
        aria-label={`Reorder ${item.navItem.label}`}
        {...attributes}
        {...listeners}
      >
        <GripVertical className="h-4 w-4" />
      </button>
      <Icon className="h-4 w-4 text-muted-foreground" />
      <span className="flex-1 text-sm text-foreground">{item.navItem.label}</span>
      {item.archived && <Badge variant="secondary">Archived</Badge>}
      <Button type="button" variant="outline" size="sm" onClick={onArchiveToggle}>
        {item.archived ? (
          <>
            <ArchiveRestore className="mr-1 h-3.5 w-3.5" /> Restore
          </>
        ) : (
          <>
            <Archive className="mr-1 h-3.5 w-3.5" /> Archive
          </>
        )}
      </Button>
    </div>
  );
}
