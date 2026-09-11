import { useQuery } from "@tanstack/react-query";
import { Sparkles, type LucideIcon } from "lucide-react";
import { Card, CardContent, cn } from "@fusion-flow/ui";
import { listStarterTemplates } from "../api";
import type { WorkflowStarterTemplate } from "../types";
import { NODE_ICONS } from "../nodes/cardSummaries";

/**
 * "Start from a template" step of the New Workflow flow (composable-
 * builder redesign, Phase 6) — a grid of cards: "Start from scratch" (the
 * previous, only behavior) plus one card per active `WorkflowStarterTemplate`
 * (`GET /workflows/starter-templates`). Picking a template is just a
 * starting point, not a lock-in — every node in the resulting graph is an
 * ordinary node the author can freely edit, remove, or add more of
 * afterward, same as `WorkflowsListPage.tsx`'s own "Cancel" always did for
 * a blank workflow.
 */

interface StarterTemplatePickerProps {
  onSelect: (template: WorkflowStarterTemplate | null) => void;
  onCancel: () => void;
}

function templateIcon(icon: string | null | undefined): LucideIcon {
  return (icon && NODE_ICONS[icon]) || Sparkles;
}

export function StarterTemplatePicker({ onSelect, onCancel }: StarterTemplatePickerProps) {
  const { data: templates = [], isLoading } = useQuery({
    queryKey: ["workflow-starter-templates"],
    queryFn: listStarterTemplates,
  });

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

          {templates.map((template) => {
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
              </button>
            );
          })}
        </div>

        <div className="flex justify-end border-t border-border pt-3">
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
