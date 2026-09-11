import { Plus, Trash2 } from "lucide-react";
import { Button, Input, cn } from "@fusion-flow/ui";
import type { ModuleCatalogEntry } from "../types";

/**
 * Hand-written editor for `whatsapp.ask_choice`'s `source` config field - a
 * Pydantic discriminated union (`StaticSource | ModuleSource`)
 * `jsonSchemaForm.ts`'s generic resolver has no support for (it falls
 * through to plain `"text"`, which would corrupt this field into a bare
 * string on save). Same "hand-written for a fixed, small, nested shape"
 * precedent `EdgeConfigDrawer.tsx` already establishes, rather than
 * generalizing `jsonSchemaForm.ts` for one field. `NodeConfigDrawer.tsx`
 * hides the generic auto-resolved row for this key and renders this
 * instead, wiring its value through React Hook Form via `setValue`.
 */

export interface StaticOption {
  id: string;
  label: string;
}

export type AskChoiceSource =
  | { kind: "static"; options: StaticOption[] }
  | {
      kind: "module";
      module: string;
      filters?: Record<string, unknown>;
      label_field?: string;
      value_field?: string;
      limit?: number;
    };

export const DEFAULT_STATIC_SOURCE: AskChoiceSource = { kind: "static", options: [{ id: "", label: "" }] };
// Narrowed to just the "module" branch (not the full `AskChoiceSource`
// union) - annotating this as `AskChoiceSource` would widen it back and
// break the ternary narrowing below wherever this constant is used as a
// fallback alongside an already-narrowed `value`.
const DEFAULT_MODULE_SOURCE: Extract<AskChoiceSource, { kind: "module" }> = {
  kind: "module",
  module: "",
  filters: {},
  label_field: "name",
  value_field: "id",
  limit: 10,
};

interface AskChoiceSourceFieldProps {
  value: AskChoiceSource | undefined;
  onChange: (next: AskChoiceSource) => void;
  modules: ModuleCatalogEntry[];
}

const segmentBase =
  "flex-1 rounded-md border px-2 py-1.5 text-xs font-medium text-center transition-colors";
const segmentInactive = "border-border bg-background text-muted-foreground hover:border-accent";
const segmentActive = "border-accent bg-accent-soft text-foreground";

export function AskChoiceSourceField({ value, onChange, modules }: AskChoiceSourceFieldProps) {
  const kind = value?.kind ?? "static";

  function switchKind(next: "static" | "module") {
    if (next === kind) return;
    onChange(next === "static" ? DEFAULT_STATIC_SOURCE : DEFAULT_MODULE_SOURCE);
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-2">
      <div className="flex gap-1.5">
        <button type="button" className={cn(segmentBase, kind === "static" ? segmentActive : segmentInactive)} onClick={() => switchKind("static")}>
          Fixed list of options
        </button>
        <button type="button" className={cn(segmentBase, kind === "module" ? segmentActive : segmentInactive)} onClick={() => switchKind("module")}>
          Pull from a module
        </button>
      </div>

      {kind === "static" ? (
        <StaticOptionsEditor
          options={value?.kind === "static" ? value.options : []}
          onChange={(options) => onChange({ kind: "static", options })}
        />
      ) : (
        <ModuleSourceEditor
          value={value && value.kind === "module" ? value : DEFAULT_MODULE_SOURCE}
          modules={modules}
          onChange={onChange}
        />
      )}
    </div>
  );
}

function StaticOptionsEditor({ options, onChange }: { options: StaticOption[]; onChange: (options: StaticOption[]) => void }) {
  function update(index: number, patch: Partial<StaticOption>) {
    onChange(options.map((option, i) => (i === index ? { ...option, ...patch } : option)));
  }

  return (
    <div className="flex flex-col gap-2">
      {options.map((option, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <Input placeholder="id (e.g. cod)" value={option.id} onChange={(e) => update(index, { id: e.target.value })} />
          <Input
            placeholder="Label shown to the customer"
            value={option.label}
            onChange={(e) => update(index, { label: e.target.value })}
          />
          <button
            type="button"
            aria-label="Remove option"
            className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
            onClick={() => onChange(options.filter((_, i) => i !== index))}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => onChange([...options, { id: "", label: "" }])}>
        <Plus className="h-3.5 w-3.5" />
        Add option
      </Button>
      <p className="text-[11px] text-muted-foreground">
        Up to 3 options render as quick-reply buttons; 4-10 render as a tap-to-open list (WhatsApp's own limits).
      </p>
    </div>
  );
}

function ModuleSourceEditor({
  value,
  modules,
  onChange,
}: {
  value: Extract<AskChoiceSource, { kind: "module" }>;
  modules: ModuleCatalogEntry[];
  onChange: (next: AskChoiceSource) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <select
        className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
        value={value.module}
        onChange={(e) => onChange({ ...value, module: e.target.value })}
      >
        <option value="">-- choose a module --</option>
        {modules.map((m) => (
          <option key={m.key} value={m.key}>
            {m.label} ({m.source === "custom" ? "your own" : "built-in"})
          </option>
        ))}
      </select>

      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-1">
          <label className="text-[11px] text-muted-foreground">Show this field as the label</label>
          <Input value={value.label_field ?? "name"} onChange={(e) => onChange({ ...value, label_field: e.target.value })} />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[11px] text-muted-foreground">Use this field as the id</label>
          <Input value={value.value_field ?? "id"} onChange={(e) => onChange({ ...value, value_field: e.target.value })} />
        </div>
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-muted-foreground">Max options to show (up to 10)</label>
        <Input
          type="number"
          min={1}
          max={10}
          value={value.limit ?? 10}
          onChange={(e) => onChange({ ...value, limit: Number(e.target.value) || 10 })}
        />
      </div>

      {/* Scope cut: a friendly per-module filter builder is out of scope
       * for this pass - a module-sourced choice always pulls every active
       * row (up to the limit above). `filters` stays an empty object. */}
      <p className="text-[11px] text-muted-foreground">
        Shows every active row from this module, up to the limit above.
      </p>
    </div>
  );
}
