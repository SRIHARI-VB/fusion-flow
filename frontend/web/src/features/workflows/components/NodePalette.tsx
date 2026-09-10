import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, GitBranch, Lock, PlayCircle, Zap } from "lucide-react";
import { cn } from "@fusion-flow/ui";
import type { NodeKind, NodeType } from "../types";

/**
 * Right-hand collapsible palette, grouped into labeled categories — per
 * `docs/design/README.md`'s reference (there: Messages/Choices/Inputs/
 * Payments/Ecommerce). Grouped by `NodeType.category` (Messaging,
 * Conditions, Integrations, Flow Control, ...) as the primary grouping,
 * with `kind` (trigger/action/condition) shown as a secondary icon badge
 * per item instead of the old flat 3-group-by-kind scheme — this finally
 * matches the reference screenshot's own taxonomy. Sourced live from
 * `GET /workflows/node-types` (raw registered types + active
 * `WorkflowNodeTemplate` rows merged - see `service.
 * list_node_types_with_templates`), so a new node type or template shows
 * up with zero palette code changes.
 */

const KIND_ICON: Record<NodeKind, typeof Zap> = { trigger: Zap, action: PlayCircle, condition: GitBranch };
const KIND_LABEL: Record<NodeKind, string> = { trigger: "Trigger", action: "Action", condition: "Condition" };

interface NodePaletteProps {
  nodeTypes: NodeType[];
  onDragStartNodeType: (nodeType: NodeType, event: React.DragEvent) => void;
}

function categoryOrder(category: string): number {
  // "Triggers" always leads (an author reaches for a trigger first when
  // building from scratch); everything else sorts alphabetically after it.
  return category === "Triggers" ? -1 : 0;
}

export function NodePalette({ nodeTypes, onDragStartNodeType }: NodePaletteProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [openGroups, setOpenGroups] = useState<Set<string>>(new Set());

  const { categories, grouped } = useMemo(() => {
    const groups = new Map<string, NodeType[]>();
    for (const nodeType of nodeTypes) {
      const list = groups.get(nodeType.category) ?? [];
      list.push(nodeType);
      groups.set(nodeType.category, list);
    }
    const cats = [...groups.keys()].sort(
      (a, b) => categoryOrder(a) - categoryOrder(b) || a.localeCompare(b),
    );
    return { categories: cats, grouped: groups };
  }, [nodeTypes]);

  // Every category starts open the first time its node types load, so
  // the whole palette is usable without an extra click; after that, the
  // user's own collapse/expand choices for already-seen categories are
  // left alone (this effect only ever adds categories, never removes).
  useEffect(() => {
    setOpenGroups((prev) => {
      const unseen = categories.filter((c) => !prev.has(c));
      if (unseen.length === 0) return prev;
      return new Set([...prev, ...unseen]);
    });
  }, [categories]);

  function toggleGroup(category: string) {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  }

  if (collapsed) {
    return (
      <div className="flex w-10 flex-col items-center gap-2 border-l border-border bg-card py-3">
        <button
          type="button"
          aria-label="Expand palette"
          className="rounded-md p-1.5 text-muted-foreground hover:bg-muted"
          onClick={() => setCollapsed(false)}
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex w-64 flex-col border-l border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <span className="flex items-center gap-1.5 text-sm font-semibold text-foreground">
          <Lock className="h-3.5 w-3.5 text-muted-foreground" />
          Node Palette
        </span>
        <button
          type="button"
          aria-label="Collapse palette"
          className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          onClick={() => setCollapsed(true)}
        >
          <ChevronRight className="h-4 w-4 rotate-180" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 py-2">
        {categories.map((category) => {
          const items = grouped.get(category) ?? [];
          const open = openGroups.has(category);

          return (
            <div key={category} className="mb-2">
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left"
                onClick={() => toggleGroup(category)}
              >
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {category}
                </span>
                {open ? (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                )}
              </button>

              {open && (
                <div className="flex flex-col gap-1 px-1 pb-1">
                  {items.map((nodeType) => {
                    const KindIcon = KIND_ICON[nodeType.kind];
                    return (
                      <div
                        key={nodeType.node_type}
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
                  })}
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
