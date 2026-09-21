import { useQuery } from "@tanstack/react-query";
import { Check, Sparkles, type LucideIcon } from "lucide-react";
import { Card, CardContent, cn } from "@fusion-flow/ui";
import { listStarterTemplates } from "../api";
import type { WorkflowPurpose, WorkflowStarterTemplate } from "../types";
import { NODE_ICONS } from "../nodes/cardSummaries";
import { useConnectorInstances } from "../../connectors/hooks";

function connectorLabel(key: string): string {
  return key.charAt(0).toUpperCase() + key.slice(1);
}

/**
 * "Start from a template" step of the New Workflow flow (composable-
 * builder redesign, Phase 6) — a grid of cards: "Start from scratch" (the
 * previous, only behavior) plus one card per active `WorkflowStarterTemplate`
 * (`GET /workflows/starter-templates`). Picking a template is just a
 * starting point, not a lock-in — every node in the resulting graph is an
 * ordinary node the author can freely edit, remove, or add more of
 * afterward, same as `WorkflowsListPage.tsx`'s own "Cancel" always did for
 * a blank workflow.
 *
 * `purpose` (the "Automation" vs. "Broadcast" choice made one step earlier
 * in the New Workflow flow) narrows the grid to templates whose own
 * `purpose` is either unset (shown for either purpose) or matches — the
 * same `template.purpose` the backend now computes server-side straight
 * from each template's own stored graph (its root trigger's registered
 * `applicable_purposes`; see `admin.service.compute_workflow_purpose`), so
 * no new DB column or admin-authored field was needed to close this gap.
 * "Start from scratch" is always shown regardless of purpose.
 */

interface StarterTemplatePickerProps {
  purpose: WorkflowPurpose;
  onSelect: (template: WorkflowStarterTemplate | null) => void;
  onCancel: () => void;
  /** Optional back-navigation to the previous step (`WorkflowsListPage.tsx`'s
   * "purpose" step) - mirrors the Back/Cancel pairing the "name" step
   * already uses to go back to this one. Omit to hide the affordance. */
  onBack?: () => void;
}

function templateIcon(icon: string | null | undefined): LucideIcon {
  return (icon && NODE_ICONS[icon]) || Sparkles;
}

export function StarterTemplatePicker({ purpose, onSelect, onCancel, onBack }: StarterTemplatePickerProps) {
  const { data: templates = [], isLoading } = useQuery({
    queryKey: ["workflow-starter-templates"],
    queryFn: listStarterTemplates,
  });
  const { data: connectorInstances = [] } = useConnectorInstances();
  const connectedKeys = new Set(connectorInstances.map((c) => c.connector_type_key));
  const visibleTemplates = purpose
    ? templates.filter((template) => template.purpose == null || template.purpose === purpose)
    : templates;

  return (
    <Card>
      <CardContent className="flex flex-col gap-3 py-4">
        <div>
          <p className="text-sm font-semibold text-foreground">Start a new workflow</p>
          <p className="text-xs text-muted-foreground">
            Start from a ready-made example, or build one from scratch — either way, every step is yours
            to edit, remove, or add to afterward.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <button
            type="button"
            className={cn(
              "flex flex-col items-start gap-1.5 rounded-md border border-dashed border-border bg-background p-3 text-left",
              "hover:border-accent hover:bg-accent-soft",
            )}
            onClick={() => onSelect(null)}
          >
            <span className="flex h-8 w-8 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <Sparkles className="h-4 w-4" />
            </span>
            <span className="text-sm font-medium text-foreground">Start from scratch</span>
            <span className="text-xs text-muted-foreground">An empty canvas — add whatever you need.</span>
          </button>

          {isLoading && (
            <p className="col-span-full text-xs text-muted-foreground">Loading templates…</p>
          )}

          {visibleTemplates.map((template) => {
            const Icon = templateIcon(template.icon);
            return (
              <button
                key={template.id}
                type="button"
                className={cn(
                  "flex flex-col items-start gap-1.5 rounded-md border border-border bg-background p-3 text-left",
                  "hover:border-accent hover:bg-accent-soft",
                )}
                onClick={() => onSelect(template)}
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-full bg-accent-soft text-accent">
                  <Icon className="h-4 w-4" />
                </span>
                <span className="text-sm font-medium text-foreground">{template.name}</span>
                {template.description && (
                  <span className="text-xs text-muted-foreground">{template.description}</span>
                )}
                {template.required_connector_type_keys && template.required_connector_type_keys.length > 0 && (
                  <span className="flex flex-wrap gap-1">
                    {template.required_connector_type_keys.map((key) => {
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
                {template.setup_notes && (
                  <span className="text-[11px] italic text-muted-foreground">{template.setup_notes}</span>
                )}
              </button>
            );
          })}
        </div>

        <div className="flex justify-end gap-4 border-t border-border pt-3">
          {onBack && (
            <button
              type="button"
              className="text-xs text-muted-foreground hover:text-foreground hover:underline"
              onClick={onBack}
            >
              Back
            </button>
          )}
          <button
            type="button"
            className="text-xs text-muted-foreground hover:text-foreground hover:underline"
            onClick={onCancel}
          >
            Cancel
          </button>
        </div>
      </CardContent>
    </Card>
  );
}
