import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button, Input, cn } from "@fusion-flow/ui";
import type { ModuleCatalogEntry } from "../types";

/**
 * Editor for a `WorkflowSchedule`'s `recipient_source` field - a
 * `{ kind: "static" } | { kind: "module" }` discriminated union, same
 * "Fixed list" / "Pull from a module" segmented-toggle shape
 * `AskChoiceSourceField.tsx` already establishes for `whatsapp.ask_choice`'s
 * `source` field, just carrying a flat list of phone numbers instead of
 * id+label option pairs.
 */

export type RecipientSource =
  | { kind: "static"; phone_numbers: string[] }
  | {
      kind: "module";
      module: string;
      filters?: Record<string, unknown>;
      phone_field: string;
    };

export const DEFAULT_STATIC_RECIPIENT_SOURCE: RecipientSource = { kind: "static", phone_numbers: [""] };
// Narrowed to just the "module" branch - see `AskChoiceSourceField.tsx`'s
// `DEFAULT_MODULE_SOURCE` comment for why this isn't annotated as the full
// `RecipientSource` union.
const DEFAULT_MODULE_RECIPIENT_SOURCE: Extract<RecipientSource, { kind: "module" }> = {
  kind: "module",
  module: "",
  filters: {},
  phone_field: "phone",
};

interface RecipientSourceFieldProps {
  value: RecipientSource | undefined;
  onChange: (next: RecipientSource) => void;
  modules: ModuleCatalogEntry[];
}

const segmentBase =
  "flex-1 rounded-md border px-2 py-1.5 text-xs font-medium text-center transition-colors";
const segmentInactive = "border-border bg-background text-muted-foreground hover:border-accent";
const segmentActive = "border-accent bg-accent-soft text-foreground";

export function RecipientSourceField({ value, onChange, modules }: RecipientSourceFieldProps) {
  const kind = value?.kind ?? "static";

  function switchKind(next: "static" | "module") {
    if (next === kind) return;
    onChange(next === "static" ? DEFAULT_STATIC_RECIPIENT_SOURCE : DEFAULT_MODULE_RECIPIENT_SOURCE);
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-2">
      <div className="flex gap-1.5">
        <button
          type="button"
          className={cn(segmentBase, kind === "static" ? segmentActive : segmentInactive)}
          onClick={() => switchKind("static")}
        >
          Fixed list of numbers
        </button>
        <button
          type="button"
          className={cn(segmentBase, kind === "module" ? segmentActive : segmentInactive)}
          onClick={() => switchKind("module")}
        >
          Pull from a module
        </button>
      </div>

      {kind === "static" ? (
        <StaticPhoneNumbersEditor
          phoneNumbers={value?.kind === "static" ? value.phone_numbers : []}
          onChange={(phone_numbers) => onChange({ kind: "static", phone_numbers })}
        />
      ) : (
        <ModuleRecipientEditor
          value={value && value.kind === "module" ? value : DEFAULT_MODULE_RECIPIENT_SOURCE}
          modules={modules}
          onChange={onChange}
        />
      )}
    </div>
  );
}

function StaticPhoneNumbersEditor({
  phoneNumbers,
  onChange,
}: {
  phoneNumbers: string[];
  onChange: (phoneNumbers: string[]) => void;
}) {
  function update(index: number, next: string) {
    onChange(phoneNumbers.map((p, i) => (i === index ? next : p)));
  }

  return (
    <div className="flex flex-col gap-2">
      {phoneNumbers.map((phone, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <Input
            placeholder="+1 555 123 4567"
            value={phone}
            onChange={(e) => update(index, e.target.value)}
          />
          <button
            type="button"
            aria-label="Remove phone number"
            className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
            onClick={() => onChange(phoneNumbers.filter((_, i) => i !== index))}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => onChange([...phoneNumbers, ""])}>
        <Plus className="h-3.5 w-3.5" />
        Add phone number
      </Button>
    </div>
  );
}

function ModuleRecipientEditor({
  value,
  modules,
  onChange,
}: {
  value: Extract<RecipientSource, { kind: "module" }>;
  modules: ModuleCatalogEntry[];
  onChange: (next: RecipientSource) => void;
}) {
  // Local draft text, not derived from `value.filters` on every keystroke -
  // re-stringifying the parsed value while the author is mid-edit (e.g.
  // right after typing a lone "{") would otherwise snap the textarea back
  // to the last valid JSON and eat whatever they just typed.
  const [filtersText, setFiltersText] = useState(() => JSON.stringify(value.filters ?? {}, null, 2));
  const [filtersError, setFiltersError] = useState(false);

  function handleFiltersChange(text: string) {
    setFiltersText(text);
    try {
      const parsed = JSON.parse(text);
      setFiltersError(false);
      onChange({ ...value, filters: parsed });
    } catch {
      setFiltersError(true);
    }
  }

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

      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-muted-foreground">Which field holds the phone number</label>
        <Input value={value.phone_field ?? "phone"} onChange={(e) => onChange({ ...value, phone_field: e.target.value })} />
      </div>

      {/* Scope cut: no friendly per-module filter builder exists for an
       * arbitrary filter shape (same reasoning as `AskChoiceSourceField`'s
       * module editor) - a small raw-JSON textarea is the narrow exception
       * here, not a precedent for the rest of this app's config forms. */}
      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-muted-foreground">Filters (advanced, optional JSON)</label>
        <textarea
          className={cn(
            "h-16 w-full rounded-md border bg-background p-2 font-mono text-xs",
            filtersError ? "border-destructive" : "border-input",
          )}
          value={filtersText}
          onChange={(e) => handleFiltersChange(e.target.value)}
        />
        {filtersError && <p className="text-[11px] text-destructive">Not valid JSON yet - keeping the last valid filters.</p>}
      </div>

      <p className="text-[11px] text-muted-foreground">
        Sends to every active row from this module that matches the filters above.
      </p>
    </div>
  );
}
