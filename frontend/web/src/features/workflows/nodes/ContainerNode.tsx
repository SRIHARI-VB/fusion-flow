import { Handle, NodeResizer, Position, type Node, type NodeProps, useNodeConnections } from "@xyflow/react";
import { Check, ChevronDown, ChevronUp, GitBranch, PlayCircle, Repeat, Shuffle, Trash2, X } from "lucide-react";
import { Badge, cn } from "@fusion-flow/ui";
import type { CardNodeData } from "../graphUtils";
import { NodeSummaryLine, collapsedPreviewRowClass } from "./NodePreview";
import { NodeInlineForm } from "../components/NodeInlineForm";

/**
 * Renders any node type whose executor opts into embedding
 * (`__meta.can_contain_children` — Loop/TryCatch/Parallel today) as a
 * larger, resizable card with a visually distinct drop-zone body, using
 * React Flow v12's native `parentId`/`extent: "parent"` node nesting —
 * the exact mechanism the pinned library version already ships (see
 * `graphUtils.enrichNodes`/`toGraphJson` for the persisted-graph side of
 * this). Child nodes are separate React Flow nodes with their own
 * `parentId` set to this node's id — React Flow positions/clips them
 * relative to this card automatically; this component only renders the
 * frame, header, and ports, never its children directly.
 *
 * Whatever config fields the container's own node type declares (e.g.
 * `flow.loop`'s `items_path`/`max_iterations`) render inline in the header
 * area via `NodeInlineForm.tsx` - same collapsed-by-default/click-to-expand
 * treatment `CardNode.tsx` gives a leaf node (see its own docstring),
 * gated by `hasOwnConfig`/`expanded` below. The resizable child drop-zone
 * body is a separate concern and is never affected by that toggle.
 */

/** Mirrors `CardNode.tsx`'s `booleanHandleLabel` - kept as its own small
 * duplicate here (rather than a shared import) since these two files
 * already each duplicate their own `PortHandle`/output-handle rendering
 * block in full; consistent visual treatment without adding a new shared
 * module for two call sites. */
function booleanHandleLabel(handleId: string): { isTrue: boolean } | null {
  const normalized = handleId.toLowerCase();
  if (normalized === "true") return { isTrue: true };
  if (normalized === "false") return { isTrue: false };
  return null;
}

const CHILD_ROLE_ICON: Record<string, typeof Repeat> = {
  loop_body: Repeat,
  try_body: GitBranch,
  parallel_branch: Shuffle,
};

// Exported so WorkflowEditorPage can use the same bounds when computing
// "did this drop/drag land inside a container" without duplicating the
// magic numbers.
export const CONTAINER_MIN_WIDTH = 360;
export const CONTAINER_MIN_HEIGHT = 220;

// The header row's own rendered height (icon badge + vertical padding +
// border) isn't exposed anywhere else — `graphUtils.fitContainerToChildren`
// needs this duplicated magic number to reserve room for it above the
// children's own bounding box when computing a snug auto-fit size. Grows
// with the container's own inline config fields (if any), so this is a
// floor, not an exact height.
export const CONTAINER_HEADER_HEIGHT = 48;

function PortHandle({
  type,
  id,
  position,
  style,
  label,
}: {
  type: "source" | "target";
  id?: string;
  position: Position;
  style?: React.CSSProperties;
  label?: string;
}) {
  const connections = useNodeConnections({ handleType: type, handleId: id });
  const connected = connections.length > 0;
  return (
    <Handle
      type={type}
      id={id}
      position={position}
      style={style}
      className={cn(
        "!h-3 !w-3 !border-2 !bg-card transition-colors",
        connected ? "!border-success" : "!border-border",
      )}
      title={label}
    />
  );
}

interface ContainerNodeProps extends NodeProps<Node<CardNodeData>> {
  /** Notifies the page-level auto-fit-to-children effect
   * (`WorkflowEditorPage.tsx`'s `containerResizingRef`) that this
   * container's own `NodeResizer` drag is in progress, so that effect
   * doesn't fight a manual resize mid-drag. */
  onResizeActiveChange?: (active: boolean) => void;
  onConfigChange?: (nodeId: string, patch: Record<string, unknown>) => void;
  onDeleteNode?: (nodeId: string) => void;
  upstreamSuggestions?: { path: string; label: string }[];
  /** Same collapsed-by-default toggle `CardNode.tsx` uses - only gates
   * this container's own inline config (e.g. `flow.loop`'s `items_path`),
   * never the child drop-zone body below it. */
  expanded?: boolean;
  onToggleExpand?: (nodeId: string) => void;
}

export function ContainerNode({
  id,
  data,
  selected,
  onResizeActiveChange,
  onConfigChange,
  onDeleteNode,
  upstreamSuggestions,
  expanded = false,
  onToggleExpand,
}: ContainerNodeProps) {
  const meta = data.__meta;
  const Icon = (meta?.child_role && CHILD_ROLE_ICON[meta.child_role]) || PlayCircle;
  const title = data.label || meta?.label || data.nodeType;
  const hasOwnConfig = Object.keys(meta?.config_schema?.properties ?? {}).length > 0;
  // Optional handles (Try/Catch) render alongside any required ones so an
  // author sees every possible exit even before wiring it.
  const outputHandles = [...(meta?.output_handles ?? []), ...(meta?.optional_output_handles ?? [])];

  return (
    <div
      className={cn(
        "flex h-full w-full flex-col rounded-lg border-2 border-dashed bg-muted/30 shadow-card",
        selected ? "border-accent ring-2 ring-accent/40" : "border-border",
      )}
      style={{ minWidth: CONTAINER_MIN_WIDTH, minHeight: CONTAINER_MIN_HEIGHT }}
    >
      <NodeResizer
        minWidth={CONTAINER_MIN_WIDTH}
        minHeight={CONTAINER_MIN_HEIGHT}
        isVisible={selected}
        lineClassName="!border-accent"
        onResizeStart={() => onResizeActiveChange?.(true)}
        onResizeEnd={() => onResizeActiveChange?.(false)}
      />

      <PortHandle type="target" position={Position.Left} style={{ top: 22 }} />

      <div className="flex flex-col gap-2 rounded-t-lg border-b border-dashed border-border bg-card px-3 py-2">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
            <Icon className="h-3.5 w-3.5" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold text-foreground">{title}</p>
            <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Flow control · {data.nodeType}
            </p>
          </div>
          {hasOwnConfig && (
            <button
              type="button"
              aria-label={expanded ? "Collapse node" : "Expand node"}
              className="nodrag shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted"
              onClick={() => onToggleExpand?.(id)}
            >
              {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>
          )}
          <button
            type="button"
            aria-label="Delete container"
            className="nodrag shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            onClick={() => onDeleteNode?.(id)}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
        {meta && hasOwnConfig && expanded && (
          <NodeInlineForm
            nodeType={meta}
            config={data.config ?? {}}
            onConfigChange={(patch) => onConfigChange?.(id, patch)}
            upstreamSuggestions={upstreamSuggestions}
          />
        )}
        {meta && hasOwnConfig && !expanded && (
          <button type="button" className={collapsedPreviewRowClass} onClick={() => onToggleExpand?.(id)}>
            <NodeSummaryLine nodeType={data.nodeType} config={data.config ?? {}} />
          </button>
        )}
      </div>

      <div className="flex-1 px-3 py-2 text-xs italic text-muted-foreground">
        Drag steps in here — they run as this container's embedded body.
      </div>

      {outputHandles.length > 0 ? (
        <div className="flex flex-col gap-2 border-t border-dashed border-border bg-card px-3 py-2">
          {outputHandles.map((handleId) => {
            const boolHandle = booleanHandleLabel(handleId);
            return (
              <div key={handleId} className="relative flex items-center justify-end gap-2 text-xs">
                {boolHandle ? (
                  <Badge variant={boolHandle.isTrue ? "success" : "destructive"} className="gap-1 font-medium">
                    {boolHandle.isTrue ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
                    {boolHandle.isTrue ? "IF · TRUE" : "ELSE · FALSE"}
                  </Badge>
                ) : (
                  <span className="capitalize text-muted-foreground">{handleId}</span>
                )}
                <PortHandle
                  type="source"
                  id={handleId}
                  position={Position.Right}
                  label={handleId}
                  style={{ position: "static", transform: "none" }}
                />
              </div>
            );
          })}
        </div>
      ) : (
        <PortHandle type="source" id="default" position={Position.Right} style={{ bottom: 22, top: "auto" }} />
      )}
    </div>
  );
}
