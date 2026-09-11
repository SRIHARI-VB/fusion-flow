import { Link } from "react-router-dom";
import { cn } from "@fusion-flow/ui";
import type { ConnectorInstance } from "../../connectors/types";
import type { NodeType } from "../types";

/**
 * Channel-first filter bar, rendered above `NodePalette` (decision 2/4 of
 * Phase 7's plan) - lets the builder pick one connected channel instance
 * (e.g. a specific WhatsApp number) to narrow the palette to just that
 * channel's automation nodes, since automation genuinely differs per
 * channel. Selectable instances are derived straight from the
 * already-entitlement-filtered `nodeTypes` response (Part A on the
 * backend) intersected with the tenant's *connected* instances - no
 * second access-control lookup needed here.
 */

interface ChannelFilterBarProps {
  instances: ConnectorInstance[];
  nodeTypes: NodeType[];
  selectedInstanceId: string | null;
  onSelect: (instanceId: string | null) => void;
}

export function ChannelFilterBar({ instances, nodeTypes, selectedInstanceId, onSelect }: ChannelFilterBarProps) {
  const selectableTypeKeys = new Set(
    nodeTypes.map((t) => t.required_connector_type_key).filter((key): key is string => Boolean(key)),
  );
  const channelInstances = instances.filter(
    (instance) => selectableTypeKeys.has(instance.connector_type_key) && instance.state === "connected",
  );

  if (channelInstances.length === 0) {
    return (
      <div className="border-b border-l border-border bg-card px-3 py-2 text-xs text-muted-foreground">
        No connected channel yet — <Link to="/connectors" className="underline">Connect one</Link>
      </div>
    );
  }

  return (
    // Fixed-width parent (matches `NodePalette`, which this now renders
    // inside of) - a wrapping row would grow taller with every connected
    // channel, so pills scroll horizontally in one line instead.
    <div className="flex gap-1.5 overflow-x-auto border-b border-l border-border bg-card px-3 py-2">
      <button
        type="button"
        aria-pressed={selectedInstanceId === null}
        onClick={() => onSelect(null)}
        className={cn(
          "shrink-0 rounded-full border px-2.5 py-1 text-xs",
          selectedInstanceId === null
            ? "border-accent bg-accent-soft text-foreground"
            : "border-border bg-background text-muted-foreground hover:border-accent",
        )}
      >
        All channels
      </button>
      {channelInstances.map((instance) => (
        <button
          key={instance.id}
          type="button"
          aria-pressed={selectedInstanceId === instance.id}
          onClick={() => onSelect(instance.id)}
          className={cn(
            "shrink-0 rounded-full border px-2.5 py-1 text-xs",
            selectedInstanceId === instance.id
              ? "border-accent bg-accent-soft text-foreground"
              : "border-border bg-background text-muted-foreground hover:border-accent",
          )}
        >
          {instance.display_name}
        </button>
      ))}
    </div>
  );
}
