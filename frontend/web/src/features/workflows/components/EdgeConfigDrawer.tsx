import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, X } from "lucide-react";
import { Button, Input } from "@fusion-flow/ui";
import type { EdgeFilter, WorkflowGraphEdgeData } from "../types";

/**
 * Selecting an edge (not a node) opens this drawer in the same right-hand
 * column slot the node palette otherwise occupies — the "edge inspector"
 * from the plan. A node's own config renders inline on its card now (see
 * `NodeInlineForm.tsx`), never in a side panel, but an edge has no card of
 * its own to render into, so it keeps this one drawer. Edge data
 * (`{filter, label}`) is a small, fixed, nested shape rather than a
 * per-node-type JSON Schema, so unlike `NodeInlineForm.tsx` this is
 * hand-written fields, not the dynamic
 * `jsonSchemaForm.ts` machinery (which only supports flat top-level
 * properties today, not a nested `filter` object) — a deliberate, small
 * scope reduction from a literal "zero new code" reading of the plan,
 * kept honest here rather than silently claimed as full reuse.
 *
 * Composable-builder redesign: the always-relevant "Label" field stays
 * visually primary; the conditional-routing filter (easy to confuse with
 * a cosmetic label, since both live in the same small panel) now sits
 * behind an "Advanced" disclosure, collapsed by default unless this edge
 * already has a filter - matching the palette's own "Advanced" default-
 * collapsed convention. Purely a visual/disclosure change - state shape
 * and `onSave` payload are unchanged.
 */

const OPERATORS = [
  { value: "eq", label: "equals" },
  { value: "neq", label: "not equals" },
  { value: "gt", label: "greater than" },
  { value: "gte", label: "greater than or equal" },
  { value: "lt", label: "less than" },
  { value: "lte", label: "less than or equal" },
  { value: "contains", label: "contains" },
];

interface EdgeConfigDrawerProps {
  edgeId: string;
  data: WorkflowGraphEdgeData | null | undefined;
  onSave: (data: WorkflowGraphEdgeData) => void;
  onClose: () => void;
}

export function EdgeConfigDrawer({ edgeId, data, onSave, onClose }: EdgeConfigDrawerProps) {
  const [label, setLabel] = useState(data?.label ?? "");
  const [filterEnabled, setFilterEnabled] = useState(!!data?.filter);
  const [filter, setFilter] = useState<EdgeFilter>(
    data?.filter ?? { field_path: "", operator: "eq", value: "" },
  );
  // Collapsed by default - open automatically when this edge already has
  // a filter, so an existing configuration is never hidden on load.
  const [advancedOpen, setAdvancedOpen] = useState(!!data?.filter);

  // Re-hydrate whenever the selected edge changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    setLabel(data?.label ?? "");
    setFilterEnabled(!!data?.filter);
    setFilter(data?.filter ?? { field_path: "", operator: "eq", value: "" });
    setAdvancedOpen(!!data?.filter);
  }, [edgeId]);

  function handleApply() {
    onSave({
      label: label.trim() || null,
      filter: filterEnabled && filter.field_path.trim() ? filter : null,
    });
  }

  return (
    <div className="flex w-80 flex-col border-l border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <div>
          <p className="text-sm font-semibold text-foreground">Edge</p>
          <p className="text-xs text-muted-foreground">Edge: {edgeId}</p>
        </div>
        <button
          type="button"
          aria-label="Close edge config"
          className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-3 py-3">
        <div className="flex flex-col gap-1.5">
          <label htmlFor="edge-label" className="text-xs font-medium text-muted-foreground">
            Label
          </label>
          <Input
            id="edge-label"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Optional canvas annotation"
          />
          <p className="text-[11px] text-muted-foreground">Pure annotation - no effect on execution.</p>
        </div>

        <hr className="border-border" />

        <div className="flex flex-col gap-2">
          <button
            type="button"
            className="flex w-full items-center justify-between text-left"
            onClick={() => setAdvancedOpen((open) => !open)}
          >
            <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Advanced</span>
            {advancedOpen ? (
              <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </button>

          {advancedOpen && (
            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 text-sm font-medium text-foreground">
                <input
                  type="checkbox"
                  checked={filterEnabled}
                  onChange={(e) => setFilterEnabled(e.target.checked)}
                />
                Only follow this edge if...
              </label>
              <p className="text-[11px] text-muted-foreground">
                A simple per-connection guard - skips this edge unless the condition matches, without needing
                a separate condition node. Most edges in a guided conversation flow don't need this - branching
                already comes from the "Ask" node itself.
              </p>

              {filterEnabled && (
            <div className="flex flex-col gap-2 rounded-md border border-border p-2">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="edge-filter-field" className="text-xs font-medium text-foreground">
                  Field path
                </label>
                <Input
                  id="edge-filter-field"
                  value={filter.field_path}
                  onChange={(e) => setFilter((f) => ({ ...f, field_path: e.target.value }))}
                  placeholder="e.g. trigger.amount"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="edge-filter-operator" className="text-xs font-medium text-foreground">
                  Operator
                </label>
                <select
                  id="edge-filter-operator"
                  className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
                  value={filter.operator}
                  onChange={(e) => setFilter((f) => ({ ...f, operator: e.target.value }))}
                >
                  {OPERATORS.map((op) => (
                    <option key={op.value} value={op.value}>
                      {op.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="edge-filter-value" className="text-xs font-medium text-foreground">
                  Value
                </label>
                <Input
                  id="edge-filter-value"
                  value={String(filter.value ?? "")}
                  onChange={(e) => setFilter((f) => ({ ...f, value: e.target.value }))}
                />
              </div>
            </div>
          )}
            </div>
          )}
        </div>

        <div className="mt-auto flex items-center gap-2 border-t border-border pt-3">
          <Button type="button" size="sm" onClick={handleApply}>
            Apply
          </Button>
        </div>
      </div>
    </div>
  );
}
