import { Handle, NodeResizer, Position, type Node, type NodeProps, useNodeConnections } from "@xyflow/react";
import { GitBranch, PlayCircle, Repeat, Shuffle } from "lucide-react";
import { cn } from "@fusion-flow/ui";
import type { CardNodeData } from "../graphUtils";

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
 */

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

export function ContainerNode({ data, selected }: NodeProps<Node<CardNodeData>>) {
  const meta = data.__meta;
  const Icon = (meta?.child_role && CHILD_ROLE_ICON[meta.child_role]) || PlayCircle;
  const title = data.label || meta?.label || data.nodeType;
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
      <NodeResizer minWidth={CONTAINER_MIN_WIDTH} minHeight={CONTAINER_MIN_HEIGHT} isVisible={selected} lineClassName="!border-accent" />

      <PortHandle type="target" position={Position.Left} style={{ top: 22 }} />

      <div className="flex items-center gap-2 rounded-t-lg border-b border-dashed border-border bg-card px-3 py-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
          <Icon className="h-3.5 w-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-foreground">{title}</p>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            Flow control · {data.nodeType}
          </p>
        </div>
      </div>

      <div className="flex-1 px-3 py-2 text-xs italic text-muted-foreground">
        Drag steps in here — they run as this container's embedded body.
      </div>

      {outputHandles.length > 0 ? (
        <div className="flex flex-col gap-2 border-t border-dashed border-border bg-card px-3 py-2">
          {outputHandles.map((handleId) => (
            <div key={handleId} className="relative flex items-center justify-end gap-2 text-xs">
              <span className="capitalize text-muted-foreground">{handleId}</span>
              <PortHandle
                type="source"
                id={handleId}
                position={Position.Right}
                label={handleId}
                style={{ position: "static", transform: "none" }}
              />
            </div>
          ))}
        </div>
      ) : (
        <PortHandle type="source" id="default" position={Position.Right} style={{ bottom: 22, top: "auto" }} />
      )}
    </div>
  );
}
