import { DraftInput, TemplateHint } from "./DraftFields";
import type { ModuleCatalogEntry } from "../types";

/**
 * Hand-written module-aware editor for `records.query`/`records.upsert`'s
 * `module`/`filters`/`fields`/`item_id` config keys. The generic resolver
 * would otherwise render `module` as a plain suggested-select fed by the
 * OLD `field_suggestions.module` computation (fixed modules only, no
 * tenant custom object types) and `filters`/`fields` as raw JSON
 * textareas - the exact "developer affordance a non-technical author
 * shouldn't need to open" this redesign exists to remove for the most
 * common node types. `NodeInlineForm.tsx` hides those generic rows for
 * these two node types and renders this instead. Plain `config`/`onChange`
 * props, not React Hook Form - see `NodeInlineForm.tsx`'s own docstring
 * for why.
 */

interface RecordModuleFieldsProps {
  nodeType: "records.query" | "records.upsert";
  modules: ModuleCatalogEntry[];
  config: Record<string, unknown>;
  onChange: (patch: Record<string, unknown>) => void;
  upstreamSuggestions?: { path: string; label: string }[];
}

export function RecordModuleFields({ nodeType, modules, config, onChange, upstreamSuggestions = [] }: RecordModuleFieldsProps) {
  const moduleKey = String(config.module ?? "");
  const defaultOperation = nodeType === "records.query" ? "list" : "create";
  const operation = String(config.operation ?? defaultOperation);
  const selectedModule = modules.find((m) => m.key === moduleKey);

  const dataKey = nodeType === "records.query" ? "filters" : "fields";
  const dataValue = (config[dataKey] as Record<string, unknown> | undefined) ?? {};

  const showItemId =
    (nodeType === "records.query" && operation === "get") || (nodeType === "records.upsert" && operation === "update");
  const showFieldsForm =
    !(nodeType === "records.query" && operation === "get") && !!selectedModule && selectedModule.fields.length > 0;

  function updateDataField(key: string, fieldValue: unknown) {
    onChange({ [dataKey]: { ...dataValue, [key]: fieldValue } });
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border p-2">
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-foreground" htmlFor="record-module">
          What kind of record?
        </label>
        <select
          id="record-module"
          className="nodrag h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
          value={moduleKey}
          onChange={(e) => onChange({ module: e.target.value })}
        >
          <option value="">-- choose a module --</option>
          {modules.map((m) => (
            <option key={m.key} value={m.key}>
              {m.label} ({m.source === "custom" ? "your own" : "built-in"})
            </option>
          ))}
        </select>
        {modules.length === 0 && <p className="text-[11px] text-muted-foreground">No modules available yet.</p>}
      </div>

      {showItemId && (
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium text-foreground" htmlFor="record-item-id">
            Record id
          </label>
          <DraftInput
            id="record-item-id"
            value={String(config.item_id ?? "")}
            onCommit={(next) => onChange({ item_id: next })}
            placeholder="e.g. {{previous_step.reply.id}}"
          />
          <TemplateHint value={String(config.item_id ?? "")} suggestions={upstreamSuggestions} />
        </div>
      )}

      {showFieldsForm && selectedModule && (
        <div className="flex flex-col gap-2">
          <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            {dataKey === "filters" ? "Filter by" : "Fields"}
          </span>
          {selectedModule.fields.map((field) => (
            <div key={field.key} className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">
                {field.label}
                {field.required && dataKey === "fields" && <span className="text-destructive"> *</span>}
              </label>
              {field.field_type === "boolean" ? (
                <input
                  type="checkbox"
                  className="nodrag h-4 w-4"
                  checked={Boolean(dataValue[field.key])}
                  onChange={(e) => updateDataField(field.key, e.target.checked)}
                />
              ) : field.field_type === "select" && field.options ? (
                <select
                  className="nodrag h-9 rounded-md border border-input bg-card px-2 text-sm"
                  value={String(dataValue[field.key] ?? "")}
                  onChange={(e) => updateDataField(field.key, e.target.value)}
                >
                  <option value="">--</option>
                  {field.options.map((opt) => (
                    <option key={String(opt)} value={String(opt)}>
                      {String(opt)}
                    </option>
                  ))}
                </select>
              ) : (
                <>
                  <DraftInput
                    type={field.field_type === "number" ? "number" : "text"}
                    value={String(dataValue[field.key] ?? "")}
                    onCommit={(next) => updateDataField(field.key, field.field_type === "number" ? Number(next) || 0 : next)}
                  />
                  <TemplateHint value={String(dataValue[field.key] ?? "")} suggestions={upstreamSuggestions} />
                </>
              )}
            </div>
          ))}
        </div>
      )}

      {!selectedModule && moduleKey && (
        <p className="text-[11px] text-muted-foreground">Loading this module's fields...</p>
      )}
    </div>
  );
}
