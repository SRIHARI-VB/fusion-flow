import { Handle, Position, type NodeProps, type Node, useNodeConnections } from "@xyflow/react";
import { Check, ChevronDown, ChevronUp, GitBranch, PlayCircle, Trash2, X, Zap } from "lucide-react";
import { Badge, cn } from "@fusion-flow/ui";
import type { CardNodeData } from "../graphUtils";
import { deriveOutputHandles, NODE_ICONS, GROUP_COLORS, DEFAULT_GROUP_COLOR } from "./cardSummaries";
import { CollapsedPreview, collapsedPreviewRowClass } from "./NodePreview";
import { NodeInlineForm } from "../components/NodeInlineForm";
import { DraftInput } from "../components/DraftFields";

/**
 * The workflow builder's single custom node component. Collapsed by
 * default: shows a compact bubble/summary preview from `NodePreview.tsx`
 * so the canvas reads as a diagram, not a wall of forms - competitor
 * WhatsApp-automation builders (ManyChat/Wati/AiSensy) all collapse a
 * message-composing step to a small chat-bubble mockup the same way.
 * Clicking the preview (or the header's chevron) expands the card to
 * show every one of the node's config fields via `NodeInlineForm.tsx` -
 * the same "configure everything on the card itself, no side panel"
 * approach as before, just no longer permanently on. One component
 * handles all three kinds (trigger/action/condition); `data.__meta`
 * (denormalized from `GET /workflows/node-types`, see
 * `graphUtils.enrichNodes`) drives the icon, port count, and labels.
 *
 * `onConfigChange`/`onLabelChange`/`onDeleteNode`/`upstreamSuggestions` are
 * all passed down from `WorkflowEditorPage.tsx`'s `nodeTypesForFlow`
 * wrapper (a plain closure, not React context - see that file) so each
 * card can commit its own field edits, rename/delete itself, and offer
 * "insert variable" suggestions without React Flow's custom-node props
 * needing to carry any of that itself.
 */

const KIND_ICON = { trigger: Zap, action: PlayCircle, condition: GitBranch } as const;

/** A condition node's `true`/`false` output handles read as a colored
 * IF/ELSE pill (green check / red X) instead of a plain dot-and-label,
 * matching the competitor builder screenshot this redesign was scoped
 * against - any other handle id (a `condition.multi_branch` case value,
 * "default", "yes"/"no" for `flow.confirm`, ...) keeps the existing plain
 * styling untouched below. */
function booleanHandleLabel(handleId: string): { isTrue: boolean } | null {
  const normalized = handleId.toLowerCase();
  if (normalized === "true") return { isTrue: true };
  if (normalized === "false") return { isTrue: false };
  return null;
}

function PortHandle({
  type,
  id,
  position,
  style,
  label,
  nested,
}: {
  type: "source" | "target";
  id?: string;
  position: Position;
  style?: React.CSSProperties;
  label?: string;
  /** True when this card is embedded inside a container (`parentId` set).
   * Nested siblings can legitimately be chained to each other via edges
   * inside the same container body, so an unconnected nested port is only
   * de-emphasized (smaller, lower-opacity) — never hidden/removed from the
   * DOM — and reverts to the normal bold styling the moment it's wired up. */
  nested?: boolean;
}) {
  const connections = useNodeConnections({ handleType: type, handleId: id });
  const connected = connections.length > 0;
  const deemphasize = nested && !connected;
  return (
    <Handle
      type={type}
      id={id}
      position={position}
      style={style}
      className={cn(
        "!border-2 !bg-card transition-colors",
        deemphasize ? "!h-2 !w-2 !opacity-40" : "!h-3 !w-3",
        connected ? "!border-success" : "!border-border",
      )}
      title={label}
    />
  );
}

interface CardNodeProps extends NodeProps<Node<CardNodeData>> {
  /** Merges `patch` into this node's `data.config` - every field on the
   * card, not just one primary one, commits through this now (the drawer
   * that used to own the "full form, one Apply button" flow is gone). */
  onConfigChange?: (nodeId: string, patch: Record<string, unknown>) => void;
  onLabelChange?: (nodeId: string, label: string) => void;
  onDeleteNode?: (nodeId: string) => void;
  /** Upstream nodes' declared output paths reachable by following edges
   * backward from this node - see `WorkflowEditorPage.tsx`'s
   * `upstreamSuggestionsByNode`. */
  upstreamSuggestions?: { path: string; label: string }[];
  /** Collapsed-by-default redesign: whether this card's full
   * `NodeInlineForm` is showing, vs. the compact bubble/summary preview
   * from `NodePreview.tsx`. Lives in `WorkflowEditorPage.tsx`'s own state
   * (see `expandedNodeIds`), not in this node's persisted `data` - purely
   * a view toggle, never part of the graph or its undo history. */
  expanded?: boolean;
  onToggleExpand?: (nodeId: string) => void;
}

export function CardNode({
  id,
  data,
  selected,
  parentId,
  onConfigChange,
  onLabelChange,
  onDeleteNode,
  upstreamSuggestions,
  expanded = false,
  onToggleExpand,
}: CardNodeProps) {
  const meta = data.__meta;
  const kind = meta?.kind ?? "action";
  const Icon = (meta?.icon && NODE_ICONS[meta.icon]) || KIND_ICON[kind];
  const outputHandles = deriveOutputHandles(data.nodeType, data.config ?? {}, meta?.output_handles ?? null);
  const groupColors = (meta?.palette_group && GROUP_COLORS[meta.palette_group]) || DEFAULT_GROUP_COLOR;
  // `parentId` is a top-level React Flow `Node` property (already exposed
  // on `NodeProps`, see `@xyflow/system`'s `NodeProps` pick list) — set
  // whenever this card is embedded inside a `flow.loop`/`flow.parallel`/
  // `flow.try_catch` container, no extra prop-threading needed for it.
  const nested = Boolean(parentId);

  function patchConfig(patch: Record<string, unknown>) {
    onConfigChange?.(id, patch);
  }

  return (
    <div
      className={cn(
        "w-80 rounded-xl border bg-card shadow-card transition-colors",
        selected ? "border-accent ring-2 ring-accent/40" : "border-border",
      )}
    >
      {kind !== "trigger" && (
        <PortHandle type="target" id={undefined} position={Position.Left} style={{ top: 22 }} nested={nested} />
      )}

      <div className={cn("flex items-center gap-2 rounded-t-xl border-b border-border px-3 py-2", groupColors.border, "border-l-4")}>
        <span
          className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full", groupColors.iconBg, groupColors.iconText)}
        >
          <Icon className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <DraftInput
            value={data.label || ""}
            onCommit={(next) => onLabelChange?.(id, next)}
            placeholder={meta?.label || data.nodeType}
            className="h-7 border-transparent bg-transparent px-1 text-sm font-semibold hover:border-border focus:border-accent focus:bg-background"
          />
          <p className="truncate px-1 text-[10px] uppercase tracking-wide text-muted-foreground" title={data.nodeType}>
            {meta?.category ?? kind}
          </p>
        </div>
        {meta && (
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
          aria-label="Delete node"
          className="nodrag shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          onClick={() => onDeleteNode?.(id)}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <div className="flex flex-col gap-3 px-3 py-2.5">
        {meta && expanded && (
          <NodeInlineForm
            nodeType={meta}
            config={data.config ?? {}}
            onConfigChange={patchConfig}
            upstreamSuggestions={upstreamSuggestions}
          />
        )}
        {meta && !expanded && (
          <button type="button" className={collapsedPreviewRowClass} onClick={() => onToggleExpand?.(id)}>
            <CollapsedPreview meta={meta} nodeType={data.nodeType} config={data.config ?? {}} />
          </button>
        )}
      </div>

      {outputHandles && outputHandles.length > 0 ? (
        <div className="flex flex-col gap-2 border-t border-border px-3 py-2">
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
                  nested={nested}
                />
              </div>
            );
          })}
        </div>
      ) : (
        <PortHandle type="source" id="default" position={Position.Right} style={{ top: 22 }} nested={nested} />
      )}

      <span className="sr-only">node id: {id}</span>
    </div>
  );
}
