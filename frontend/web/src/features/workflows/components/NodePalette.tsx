import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight, GitBranch, Lock, PlayCircle, Zap } from "lucide-react";
import { cn } from "@fusion-flow/ui";
import type { NodeKind, NodeType } from "../types";

/**
 * Right-hand collapsible palette, grouped into labeled categories — per
 * `docs/design/README.md`'s reference (there: Messages/Choices/Inputs/
 * Payments/Ecommerce). Mapped here to our own taxonomy: Triggers/Actions/
 * Conditions, one group per `NodeType.kind`, sourced live from
 * `GET /workflows/node-types` (so a future connector-contributed node type
 * — e.g. `whatsapp.message_received` — shows up with zero palette changes).
 */

const KIND_ORDER: NodeKind[] = ["trigger", "action", "condition"];
const KIND_ICON = { trigger: Zap, action: PlayCircle, condition: GitBranch } as const;
const KIND_GROUP_LABEL: Record<NodeKind, string> = {
  trigger: "Triggers",
  action: "Actions",
  condition: "Conditions",
};

interface NodePaletteProps {
  nodeTypes: NodeType[];
  onDragStartNodeType: (nodeType: NodeType, event: React.DragEvent) => void;
}

export function NodePalette({ nodeTypes, onDragStartNodeType }: NodePaletteProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [openGroups, setOpenGroups] = useState<Set<NodeKind>>(new Set(KIND_ORDER));

  const grouped = useMemo(() => {
    const groups = new Map<NodeKind, NodeType[]>();
    for (const kind of KIND_ORDER) groups.set(kind, []);
    for (const nodeType of nodeTypes) groups.get(nodeType.kind)?.push(nodeType);
    return groups;
  }, [nodeTypes]);

  function toggleGroup(kind: NodeKind) {
    setOpenGroups((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
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
        {KIND_ORDER.map((kind) => {
          const items = grouped.get(kind) ?? [];
          if (items.length === 0) return null;
          const Icon = KIND_ICON[kind];
          const open = openGroups.has(kind);

          return (
            <div key={kind} className="mb-2">
              <button
                type="button"
                className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left"
                onClick={() => toggleGroup(kind)}
              >
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {KIND_GROUP_LABEL[kind]}
                </span>
                {open ? (
                  <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                )}
              </button>

              {open && (
                <div className="flex flex-col gap-1 px-1 pb-1">
                  {items.map((nodeType) => (
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
                      <Icon className="h-3.5 w-3.5 shrink-0 text-accent" />
                      <span className="truncate">{nodeType.label}</span>
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
