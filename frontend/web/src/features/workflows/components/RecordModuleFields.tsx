import type { UseFormSetValue, UseFormWatch } from "react-hook-form";
import { Input } from "@fusion-flow/ui";
import type { ModuleCatalogEntry } from "../types";

/**
 * Hand-written module-aware editor for `records.query`/`records.upsert`'s
 * `module`/`filters`/`fields`/`item_id` config keys. The generic resolver
 * would otherwise render `module` as a plain suggested-select fed by the
 * OLD `field_suggestions.module` computation (fixed modules only, no
 * tenant custom object types) and `filters`/`fields` as raw JSON
 * textareas - the exact "developer affordance a non-technical author
 * shouldn't need to open" this redesign exists to remove for the most
 * common node types. `NodeConfigDrawer.tsx` hides those generic rows for
 * these two node types and renders this instead.
 */

interface RecordModuleFieldsProps {
  nodeType: "records.query" | "records.upsert";
  modules: ModuleCatalogEntry[];
  watch: UseFormWatch<Record<string, unknown>>;
  setValue: UseFormSetValue<Record<string, unknown>>;
}

export function RecordModuleFields({ nodeType, modules, watch, setValue }: RecordModuleFieldsProps) {
  const moduleKey = String(watch("module") ?? "");
  const defaultOperation = nodeType === "records.query" ? "list" : "create";
  const operation = String(watch("operation") ?? defaultOperation);
  const selectedModule = modules.find((m) => m.key === moduleKey);

  const dataKey = nodeType === "records.query" ? "filters" : "fields";
  const dataValue = (watch(dataKey) as Record<string, unknown> | undefined) ?? {};

  const showItemId =
    (nodeType === "records.query" && operation === "get") || (nodeType === "records.upsert" && operation === "update");
  const showFieldsForm =
    !(nodeType === "records.query" && operation === "get") && !!selectedModule && selectedModule.fields.length > 0;

  function updateDataField(key: string, fieldValue: unknown) {
    setValue(dataKey, { ...dataValue, [key]: fieldValue }, { shouldDirty: true });
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border border-border p-2">
      <div className="flex flex-col gap-1.5">
        <label className="text-xs font-medium text-foreground" htmlFor="record-module">
          What kind of record?
        </label>
        <select
          id="record-module"
          className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
          value={moduleKey}
          onChange={(e) => setValue("module", e.target.value, { shouldDirty: true })}
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
          <Input
            id="record-item-id"
            value={String(watch("item_id") ?? "")}
            onChange={(e) => setValue("item_id", e.target.value, { shouldDirty: true })}
            placeholder="e.g. {{previous_step.reply.id}}"
          />
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
                  className="h-4 w-4"
                  checked={Boolean(dataValue[field.key])}
                  onChange={(e) => updateDataField(field.key, e.target.checked)}
                />
              ) : field.field_type === "select" && field.options ? (
                <select
                  className="h-9 rounded-md border border-input bg-card px-2 text-sm"
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
                <Input
                  type={field.field_type === "number" ? "number" : "text"}
                  value={String(dataValue[field.key] ?? "")}
                  onChange={(e) => updateDataField(field.key, e.target.value)}
                />
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
