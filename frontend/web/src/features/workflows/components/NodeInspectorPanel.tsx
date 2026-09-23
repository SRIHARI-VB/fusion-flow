import { Trash2, X } from "lucide-react";
import type { Node } from "@xyflow/react";
import type { CardNodeData } from "../graphUtils";
import { NodeInlineForm } from "./NodeInlineForm";
import { DraftInput } from "./DraftFields";

/**
 * Selecting exactly one node opens this in the same right-hand-column slot
 * `EdgeConfigDrawer.tsx` already uses for a selected edge - same idea, for
 * a node: a dedicated, full-height editing surface instead of squeezing
 * `NodeInlineForm` into a 320px-wide card that's also subject to the
 * canvas's own zoom level (so "small text, small inputs" at anything less
 * than 100% zoom, on top of the card's own width limit). The card's inline
 * expand/collapse (`CardNode.tsx`) still works exactly as before - this is
 * an additional, roomier way to edit the same `config` through the exact
 * same `NodeInlineForm`, not a replacement for it.
 */

interface NodeInspectorPanelProps {
  node: Node<CardNodeData>;
  onConfigChange: (nodeId: string, patch: Record<string, unknown>) => void;
  onLabelChange: (nodeId: string, label: string) => void;
  onDeleteNode: (nodeId: string) => void;
  onClose: () => void;
  upstreamSuggestions: { path: string; label: string }[];
}

export function NodeInspectorPanel({
  node,
  onConfigChange,
  onLabelChange,
  onDeleteNode,
  onClose,
  upstreamSuggestions,
}: NodeInspectorPanelProps) {
  const meta = node.data.__meta;

  return (
    <div className="flex w-96 flex-col border-l border-border bg-card">
      <div className="flex items-start justify-between gap-2 border-b border-border px-3 py-2.5">
        <div className="min-w-0 flex-1">
          <DraftInput
            value={node.data.label || ""}
            onCommit={(next) => onLabelChange(node.id, next)}
            placeholder={meta?.label || node.data.nodeType}
            className="h-8 border-transparent bg-transparent px-1 text-sm font-semibold hover:border-border focus:border-accent focus:bg-background"
          />
          <p className="truncate px-1 text-[10px] uppercase tracking-wide text-muted-foreground" title={node.data.nodeType}>
            {meta?.category ?? "Node"}
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button
            type="button"
            aria-label="Delete node"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            onClick={() => onDeleteNode(node.id)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Close node inspector"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {meta ? (
          <NodeInlineForm
            nodeType={meta}
            config={node.data.config ?? {}}
            onConfigChange={(patch) => onConfigChange(node.id, patch)}
            upstreamSuggestions={upstreamSuggestions}
          />
        ) : (
          <p className="text-xs italic text-muted-foreground">Loading node type...</p>
        )}
      </div>
    </div>
  );
}
