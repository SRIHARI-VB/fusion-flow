import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, GitBranch, Lock, PlayCircle, Zap } from "lucide-react";
import { cn } from "@fusion-flow/ui";
import type { ConnectorInstance } from "../../connectors/types";
import type { NodeKind, NodeType } from "../types";
import { ChannelFilterBar } from "./ChannelFilterBar";

/**
 * Right-hand collapsible palette, grouped into labeled task-oriented
 * buckets (composable-builder redesign) — primary grouping is now
 * `NodeType.palette_group` ("Talk to Customer" / "Records" / "Payments" /
 * "Flow Control" / "Advanced" / "Triggers", every entry always has one -
 * see `engine.registry.NodeTypeMeta`'s docstring), with `category` as a
 * secondary sub-header inside each group (only shown when a group mixes
 * more than one category, e.g. "Records" spans Ecommerce/Support/
 * Customers/etc.) and `subcategory` as a third level unchanged from
 * before (e.g. "Messages" > "Media"/"Location"/"Contact"/"Template" for
 * the WhatsApp send nodes). `kind` (trigger/action/condition) still shows
 * as a secondary icon badge per item. Sourced live from
 * `GET /workflows/node-types` (raw registered types + active
 * `WorkflowNodeTemplate` rows merged - see `service.
 * list_node_types_with_templates`), so a new node type or template shows
 * up with zero palette code changes.
 */

const KIND_ICON: Record<NodeKind, typeof Zap> = { trigger: Zap, action: PlayCircle, condition: GitBranch };
const KIND_LABEL: Record<NodeKind, string> = { trigger: "Trigger", action: "Action", condition: "Condition" };

/** Left-border accent per palette group, purely for scannability - an
 * unmapped group falls back to `DEFAULT_GROUP_COLOR`, never breaking for
 * a future group this map hasn't caught up with yet. */
const GROUP_COLORS: Record<string, string> = {
  Triggers: "border-l-red-500",
  "Talk to Customer": "border-l-emerald-500",
  Records: "border-l-blue-500",
  Payments: "border-l-amber-500",
  "Flow Control": "border-l-slate-500",
  Advanced: "border-l-gray-400",
};
const DEFAULT_GROUP_COLOR = "border-l-gray-400";

/** Fixed display order for the known palette groups - "Triggers" leads
 * (an author reaches for a trigger first when building from scratch),
 * then task-oriented groups roughly in the order a guided conversation
 * flow is built, "Advanced" last (raw generic-executor/legacy nodes,
 * collapsed by default - see `NodePalette`'s `openGroups` effect below).
 * A future group not in this list sorts alphabetically after all of
 * these, rather than breaking. */
const GROUP_ORDER = ["Triggers", "Talk to Customer", "Records", "Payments", "Flow Control", "Advanced"];

function paletteGroupOrder(group: string): number {
  const index = GROUP_ORDER.indexOf(group);
  return index === -1 ? GROUP_ORDER.length : index;
}

interface NodePaletteProps {
  nodeTypes: NodeType[];
  onDragStartNodeType: (nodeType: NodeType, event: React.DragEvent) => void;
  /** The channel filter bar used to live as a separate sibling above this
   * panel, sized independently of it - which is exactly why its width
   * never matched and collapsing one didn't collapse the other. It's now
   * rendered *inside* this same fixed-width, single-collapse-toggle
   * container instead, so both always share one width and one open/closed
   * state. `allNodeTypes` is deliberately the *unfiltered* node-type list
   * (unlike this component's own `nodeTypes`, which is already narrowed to
   * the selected channel) - `ChannelFilterBar` needs the full list to know
   * which connector types exist at all. */
  allNodeTypes: NodeType[];
  channelInstances: ConnectorInstance[];
  selectedChannelInstanceId: string | null;
  onSelectChannel: (instanceId: string | null) => void;
}

interface CategorySection {
  category: string;
  directItems: NodeType[];
  subgroups: Array<{ subcategory: string; items: NodeType[] }>;
}

interface PaletteGroupSection {
  group: string;
  categories: CategorySection[];
  /** Only render each category's own sub-header when a group actually
   * mixes more than one category - a group with a single category (e.g.
   * "Payments" today) would otherwise show one redundant, single-item
   * sub-header repeating the group's own name in substance. */
  showCategoryHeaders: boolean;
}

function buildGroups(nodeTypes: NodeType[]): PaletteGroupSection[] {
  const byGroup = new Map<string, NodeType[]>();
  for (const nodeType of nodeTypes) {
    const list = byGroup.get(nodeType.palette_group) ?? [];
    list.push(nodeType);
    byGroup.set(nodeType.palette_group, list);
  }

  const groupNames = [...byGroup.keys()].sort(
    (a, b) => paletteGroupOrder(a) - paletteGroupOrder(b) || a.localeCompare(b),
  );

  return groupNames.map((group) => {
    const items = byGroup.get(group) ?? [];
    const categoryOrder: string[] = [];
    const byCategory = new Map<string, NodeType[]>();
    for (const item of items) {
      if (!byCategory.has(item.category)) {
        categoryOrder.push(item.category);
        byCategory.set(item.category, []);
      }
      byCategory.get(item.category)!.push(item);
    }

    const categories: CategorySection[] = categoryOrder.map((category) => {
      const categoryItems = byCategory.get(category) ?? [];
      const directItems: NodeType[] = [];
      const subgroupOrder: string[] = [];
      const subgroupMap = new Map<string, NodeType[]>();

      for (const item of categoryItems) {
        if (!item.subcategory) {
          directItems.push(item);
          continue;
        }
        if (!subgroupMap.has(item.subcategory)) {
          subgroupOrder.push(item.subcategory);
          subgroupMap.set(item.subcategory, []);
        }
        subgroupMap.get(item.subcategory)!.push(item);
      }

      return {
        category,
        directItems,
        subgroups: subgroupOrder.map((subcategory) => ({ subcategory, items: subgroupMap.get(subcategory)! })),
      };
    });

    return { group, categories, showCategoryHeaders: categoryOrder.length > 1 };
  });
}

function PaletteItem({ nodeType, onDragStartNodeType }: { nodeType: NodeType; onDragStartNodeType: NodePaletteProps["onDragStartNodeType"] }) {
  const KindIcon = KIND_ICON[nodeType.kind];
  return (
    <div
      draggable
      onDragStart={(event) => onDragStartNodeType(nodeType, event)}
      title={nodeType.description}
      className={cn(
        "flex cursor-grab items-center gap-2 rounded-md border border-border bg-background px-2 py-1.5",
        "text-xs text-foreground hover:border-accent hover:bg-accent-soft active:cursor-grabbing",
      )}
    >
      <span className="truncate">{nodeType.label}</span>
      <span
        className="ml-auto flex shrink-0 items-center gap-1 rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground"
        title={KIND_LABEL[nodeType.kind]}
      >
        <KindIcon className="h-2.5 w-2.5" />
      </span>
    </div>
  );
}

export function NodePalette({
  nodeTypes,
  onDragStartNodeType,
  allNodeTypes,
  channelInstances,
  selectedChannelInstanceId,
  onSelectChannel,
}: NodePaletteProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set());

  const groups = useMemo(() => buildGroups(nodeTypes), [nodeTypes]);

  // Every group starts open the first time its node types load, so the
  // whole palette is usable without an extra click - except "Advanced"
  // (raw generic-executor/legacy nodes), which starts collapsed: it's one
  // click away, not hidden, but a non-technical author shouldn't see it
  // as the default view. After the first sighting, the user's own
  // collapse/expand choices for already-seen groups are left alone (this
  // effect only ever adds groups, never removes/re-adds one).
  useEffect(() => {
    setOpenGroups((prev) => {
      const unseen = groups.map((g) => g.group).filter((g) => g !== "Advanced" && !prev.has(g));
      if (unseen.length === 0) return prev;
      return new Set([...prev, ...unseen]);
    });
  }, [groups]);

  function toggleGroup(group: string) {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(group)) next.delete(group);
      else next.add(group);
      return next;
    });
  }

  if (collapsed) {
    return (
      <div className="flex h-full min-h-0 w-10 flex-col items-center gap-2 border-l border-border bg-card py-3">
        {/* Docked on the right edge: collapsed -> expanded pulls the panel
            back in *from* the right, so this arrow points left. */}
        <button
          type="button"
          aria-label="Expand palette"
          className="rounded-md p-1.5 text-muted-foreground hover:bg-muted"
          onClick={() => setCollapsed(false)}
        >
          <ChevronRight className="h-4 w-4 rotate-180" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex w-64 min-h-0 shrink-0 flex-col border-l border-border bg-card">
      <ChannelFilterBar
        instances={channelInstances}
        nodeTypes={allNodeTypes}
        selectedInstanceId={selectedChannelInstanceId}
        onSelect={onSelectChannel}
      />
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <Lock className="h-3.5 w-3.5 text-muted-foreground" />
          Node Palette
        </span>
        {/* Expanded -> collapsed pushes the panel away *toward* the right
            edge it's docked on, so this arrow points right (no rotation -
            the opposite of the expand button above). */}
        <button
          type="button"
          aria-label="Collapse palette"
          className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          onClick={() => setCollapsed(true)}
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {groups.map(({ group, categories, showCategoryHeaders }) => {
          const open = openGroups.has(group);

          return (
            <div key={group} className={cn("mb-2 border-l-4 pl-1", GROUP_COLORS[group] ?? DEFAULT_GROUP_COLOR)}>
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left"
                onClick={() => toggleGroup(group)}
              >
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">{group}</span>
                {open ? (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                )}
              </button>

              {open && (
                <div className="flex flex-col gap-2 px-1 pb-1">
                  {categories.map(({ category, directItems, subgroups }) => (
                    <div key={category} className="flex flex-col gap-1">
                      {showCategoryHeaders && (
                        <span className="pl-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground/80">
                          {category}
                        </span>
                      )}

                      {directItems.length > 0 && (
                        <div className="flex flex-col gap-1">
                          {directItems.map((nodeType) => (
                            <PaletteItem key={nodeType.node_type} nodeType={nodeType} onDragStartNodeType={onDragStartNodeType} />
                          ))}
                        </div>
                      )}

                      {subgroups.map(({ subcategory, items }) => (
                        <div key={subcategory} className="flex flex-col gap-1 pl-2">
                          <span className="pl-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">
                            {subcategory}
                          </span>
                          {items.map((nodeType) => (
                            <PaletteItem key={nodeType.node_type} nodeType={nodeType} onDragStartNodeType={onDragStartNodeType} />
                          ))}
                        </div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}

        {nodeTypes.length === 0 && (
          <p className="px-2 py-4 text-xs text-muted-foreground">No node types available.</p>
        )}
      </div>
    </div>
  );
}
