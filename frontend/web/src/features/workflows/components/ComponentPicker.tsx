import { useQuery } from "@tanstack/react-query";
import { Blocks, Check, X, type LucideIcon } from "lucide-react";
import { Badge, Button, cn } from "@fusion-flow/ui";
import { listComponents } from "../api";
import type { WorkflowComponent } from "../types";
import { NODE_ICONS } from "../nodes/cardSummaries";
import { useConnectorInstances } from "../../connectors/hooks";

function connectorLabel(key: string): string {
  return key.charAt(0).toUpperCase() + key.slice(1);
}

/**
 * "Insert a Component" — a floating overlay (same treatment
 * `SaveComponentDialog.tsx`/the test-run panel already use) listing every
 * fragment this tenant can drop into the workflow currently open: the
 * admin-curated catalog plus this tenant's own saved selections
 * (`GET /workflows/components`, distinguished by the `source` badge).
 * Selecting one merges its nodes+edges into the canvas — see
 * `WorkflowEditorPage.tsx`'s `handleInsertComponent`.
 */

interface ComponentPickerProps {
  onSelect: (component: WorkflowComponent) => void;
  onClose: () => void;
  isInserting?: boolean;
}

function componentIcon(icon: string | null | undefined): LucideIcon {
  return (icon && NODE_ICONS[icon]) || Blocks;
}

export function ComponentPicker({ onSelect, onClose, isInserting }: ComponentPickerProps) {
  const { data: components = [], isLoading } = useQuery({
    queryKey: ["workflow-components"],
    queryFn: listComponents,
  });
  const { data: connectorInstances = [] } = useConnectorInstances();
  const connectedKeys = new Set(connectorInstances.map((c) => c.connector_type_key));

  return (
    <div className="absolute inset-0 z-20 flex items-start justify-center overflow-y-auto bg-background/70 p-6">
      <div className="w-full max-w-2xl rounded-lg border border-border bg-card p-4 shadow-lg">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-sm font-semibold text-foreground">Insert a component</p>
            <p className="text-xs text-muted-foreground">
              Drop a ready-made chunk of nodes into this workflow — some wiring may be left for you to
              connect, the same way a template's connector fields are.
            </p>
          </div>
          <button
            type="button"
            aria-label="Close"
            className="rounded-md p-1 text-muted-foreground hover:bg-muted"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {isLoading && <p className="text-xs text-muted-foreground">Loading components…</p>}
        {!isLoading && components.length === 0 && (
          <p className="text-xs text-muted-foreground">No components available yet.</p>
        )}

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {components.map((component) => {
            const Icon = componentIcon(component.icon);
            return (
              <button
                key={component.id}
                type="button"
                disabled={isInserting}
                className={cn(
                  "flex flex-col items-start gap-1.5 rounded-md border border-border bg-background p-3 text-left",
                  "hover:border-accent hover:bg-accent-soft disabled:opacity-60",
                )}
                onClick={() => onSelect(component)}
              >
                <div className="flex w-full items-center justify-between gap-2">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-soft text-accent">
                    <Icon className="h-4 w-4" />
                  </span>
                  <Badge variant={component.source === "admin" ? "default" : "outline"}>
                    {component.source === "admin" ? "Built-in" : "Your own"}
                  </Badge>
                </div>
                <span className="text-sm font-medium text-foreground">{component.name}</span>
                {component.description && (
                  <span className="text-xs text-muted-foreground">{component.description}</span>
                )}
                {component.required_connector_type_keys && component.required_connector_type_keys.length > 0 && (
                  <span className="flex flex-wrap gap-1">
                    {component.required_connector_type_keys.map((key) => {
                      const connected = connectedKeys.has(key);
                      return (
                        <span
                          key={key}
                          className={cn(
                            "inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px]",
                            connected
                              ? "border-success/40 bg-success/10 text-success"
                              : "border-border bg-muted text-muted-foreground",
                          )}
                        >
                          {connected && <Check className="h-2.5 w-2.5" />}
                          {connectorLabel(key)}
                        </span>
                      );
                    })}
                  </span>
                )}
                {component.setup_notes && (
                  <span className="text-[11px] italic text-muted-foreground">{component.setup_notes}</span>
                )}
              </button>
            );
          })}
        </div>

        <div className="mt-3 flex justify-end border-t border-border pt-3">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
