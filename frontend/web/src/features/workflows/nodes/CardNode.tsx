import { Handle, Position, type NodeProps, type Node, useNodeConnections } from "@xyflow/react";
import { GitBranch, PlayCircle, Zap } from "lucide-react";
import { cn } from "@fusion-flow/ui";
import type { CardNodeData } from "../graphUtils";

/**
 * The workflow builder's single custom node component — rounded card with
 * an icon+title header and a body preview, per `docs/design/README.md`'s
 * "Workflow builder" reference. One component handles all three kinds
 * (trigger/action/condition); `data.__meta` (denormalized from
 * `GET /workflows/node-types`, see `graphUtils.enrichNodes`) drives the
 * icon, port count, and labels.
 */

const KIND_ICON = { trigger: Zap, action: PlayCircle, condition: GitBranch } as const;
const KIND_LABEL = { trigger: "Trigger", action: "Action", condition: "Condition" } as const;

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

export function CardNode({ id, data, selected }: NodeProps<Node<CardNodeData>>) {
  const meta = data.__meta;
  const kind = meta?.kind ?? "action";
  const Icon = KIND_ICON[kind];
  const title = data.label || meta?.label || data.nodeType;
  const outputHandles = meta?.output_handles ?? null;

  const configEntries = Object.entries(data.config ?? {}).filter(([, v]) => v !== null && v !== "");

  return (
    <div
      className={cn(
        "w-64 rounded-lg border bg-card shadow-card",
        selected ? "border-accent ring-2 ring-accent/40" : "border-border",
      )}
    >
      {kind !== "trigger" && (
        <PortHandle type="target" id={undefined} position={Position.Left} style={{ top: 22 }} />
      )}

      <div className="flex items-center gap-2 rounded-t-lg border-b border-border px-3 py-2">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
          <Icon className="h-3.5 w-3.5" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-foreground">{title}</p>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
            {KIND_LABEL[kind]} · {data.nodeType}
          </p>
        </div>
      </div>

      <div className="px-3 py-2 text-xs text-muted-foreground">
        {configEntries.length === 0 ? (
          <span className="italic">Not configured yet</span>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {configEntries.slice(0, 3).map(([key, value]) => (
              <li key={key} className="truncate">
                <span className="font-medium text-foreground">{key}:</span> {String(value)}
              </li>
            ))}
          </ul>
        )}
      </div>

      {outputHandles && outputHandles.length > 0 ? (
        <div className="flex flex-col gap-2 border-t border-border px-3 py-2">
          {outputHandles.map((handleId, index) => (
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
        <PortHandle type="source" id="default" position={Position.Right} style={{ top: 22 }} />
      )}

      <span className="sr-only">node id: {id}</span>
    </div>
  );
}
