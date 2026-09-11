import { useEffect, useMemo } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { X } from "lucide-react";
import { z } from "zod";
import { Button, Input, Textarea } from "@fusion-flow/ui";
import type { NodeType } from "../types";
import { listModules } from "../api";
import { buildDefaultValues, buildZodSchema, resolveFields } from "../jsonSchemaForm";
import { ArrayObjectField, ArrayTextField, JsonObjectField } from "./DynamicArrayFields";
import { InsertVariableMenu } from "./InsertVariableMenu";
import { AskChoiceSourceField, DEFAULT_STATIC_SOURCE, type AskChoiceSource } from "./AskChoiceSourceField";
import { RecordModuleFields } from "./RecordModuleFields";

/**
 * Per-node config drawer — a dynamic form built from the selected node's
 * `config_schema` (React Hook Form + Zod, same conceptual approach as
 * `features/custom-fields/DynamicCustomFieldsFields.tsx`). Replaces the
 * palette in the same right-hand column while a node is selected.
 *
 * Two node types get a bounded, hand-written override on top of the
 * generic schema-driven rendering (see `AskChoiceSourceField.tsx`/
 * `RecordModuleFields.tsx`'s own docstrings for why): their
 * auto-resolved field rows are hidden via `HIDDEN_FIELD_KEYS_BY_NODE_TYPE`
 * and replaced with a dedicated sub-component wired into the same React
 * Hook Form instance via `watch`/`setValue`.
 */

/** Config keys these two node-type families render with a bespoke editor
 * instead of the generic per-field loop - see this file's module
 * docstring. */
const HIDDEN_FIELD_KEYS_BY_NODE_TYPE: Record<string, string[]> = {
  "whatsapp.ask_choice": ["source"],
  "records.query": ["module", "filters", "item_id"],
  "records.upsert": ["module", "fields", "item_id"],
};

interface NodeConfigDrawerProps {
  nodeId: string;
  nodeType: NodeType;
  label: string;
  config: Record<string, unknown>;
  onLabelChange: (label: string) => void;
  onSave: (config: Record<string, unknown>) => void;
  onClose: () => void;
  onDelete: () => void;
  /** Upstream nodes' declared output paths, reachable by following edges
   * backward from this node (see `WorkflowEditorPage.tsx`) - offered via
   * an "insert variable" picker next to freeform reference fields. */
  upstreamSuggestions?: { path: string; label: string }[];
}

export function NodeConfigDrawer({
  nodeId,
  nodeType,
  label,
  config,
  onLabelChange,
  onSave,
  onClose,
  onDelete,
  upstreamSuggestions = [],
}: NodeConfigDrawerProps) {
  const { data: modules = [] } = useQuery({ queryKey: ["workflow-modules"], queryFn: listModules });

  const hiddenFieldKeys = HIDDEN_FIELD_KEYS_BY_NODE_TYPE[nodeType.node_type];
  const fields = resolveFields(nodeType.config_schema, nodeType.field_suggestions).filter(
    (field) => !hiddenFieldKeys?.includes(field.key),
  );

  // `whatsapp.ask_choice`'s `source` is a Pydantic discriminated union the
  // generic resolver can't express (see `AskChoiceSourceField.tsx`'s
  // docstring) - it falls through to a plain `"text"`/`z.string()` field,
  // which would silently corrupt this key into a bare string on save
  // (`AskChoiceSourceField` writes a real object into it). Overriding just
  // this one key to `z.any()` is the minimal fix; everything else keeps
  // the fully generic schema unchanged.
  const schema = useMemo(() => {
    const base = buildZodSchema(nodeType.config_schema, nodeType.field_suggestions);
    if (nodeType.node_type === "whatsapp.ask_choice" && base instanceof z.ZodObject) {
      return base.extend({ source: z.any() });
    }
    return base;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeType]);

  const {
    register,
    control,
    handleSubmit,
    reset,
    setValue,
    getValues,
    watch,
    formState: { errors, isDirty },
  } = useForm<Record<string, unknown>>({
    resolver: zodResolver(schema as never),
    defaultValues: buildDefaultValues(nodeType.config_schema, config, nodeType.field_suggestions),
  });

  // Re-hydrate the form whenever the selected node changes (nodeId is the
  // stable identity signal here — `config` is a new object reference on
  // every render otherwise).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    reset(buildDefaultValues(nodeType.config_schema, config, nodeType.field_suggestions));
    // A brand-new `whatsapp.ask_choice` node's `source` starts as `{}`
    // (no config yet) - `buildDefaultValues` has no notion of this key's
    // real (object) shape, so it would default to `""` (the generic
    // "text" fallback). Correct it to a real, publishable default the
    // instant the node is selected, rather than only when the author
    // happens to touch `AskChoiceSourceField` themselves.
    if (nodeType.node_type === "whatsapp.ask_choice" && (!config.source || typeof config.source !== "object")) {
      setValue("source", DEFAULT_STATIC_SOURCE, { shouldDirty: false });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeId]);

  function insertVariable(key: string, path: string) {
    const current = getValues(key);
    setValue(key, `${typeof current === "string" ? current : ""}{{${path}}}`, { shouldDirty: true });
  }

  function onSubmit(values: Record<string, unknown>) {
    onSave(values);
  }

  return (
    <div className="flex w-80 flex-col border-l border-border bg-card">
      <div className="flex items-center justify-between border-b border-border px-3 py-2.5">
        <div>
          <p className="text-sm font-semibold text-foreground">{nodeType.label}</p>
          <p className="text-xs text-muted-foreground">Node: {nodeId}</p>
        </div>
        <button
          type="button"
          aria-label="Close config"
          className="rounded-md p-1 text-muted-foreground hover:bg-muted"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <form className="flex flex-1 flex-col gap-4 overflow-y-auto px-3 py-3" onSubmit={handleSubmit(onSubmit)}>
        <div className="flex flex-col gap-1.5">
          <label htmlFor="node-label" className="text-xs font-medium text-muted-foreground">
            Label
          </label>
          <Input
            id="node-label"
            value={label}
            onChange={(e) => onLabelChange(e.target.value)}
            placeholder={nodeType.label}
          />
        </div>

        {fields.length === 0 && (
          <p className="text-xs italic text-muted-foreground">This node type has no configurable fields.</p>
        )}

        {fields.map((field) => (
          <div key={field.key} className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <label htmlFor={field.key} className="text-xs font-medium text-foreground">
                {field.label}
                {field.required && <span className="text-destructive"> *</span>}
              </label>
              {(field.kind === "text" || field.kind === "textarea") && (
                <InsertVariableMenu suggestions={upstreamSuggestions} onInsert={(path) => insertVariable(field.key, path)} />
              )}
            </div>

            {field.kind === "boolean" && (
              <input
                id={field.key}
                type="checkbox"
                className="h-4 w-4 rounded border-input"
                {...register(field.key)}
              />
            )}

            {field.kind === "select" && (
              <select
                id={field.key}
                className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
                {...register(field.key)}
              >
                {!field.required && <option value="">--</option>}
                {(field.options ?? []).map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            )}

            {field.kind === "number" && (
              <Input id={field.key} type="number" step="any" {...register(field.key)} />
            )}

            {field.kind === "text" && <Input id={field.key} {...register(field.key)} />}

            {field.kind === "textarea" && <Textarea id={field.key} {...register(field.key)} />}

            {field.kind === "suggested_select" && (
              <>
                <select
                  id={field.key}
                  className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
                  {...register(field.key)}
                >
                  {!field.required && <option value="">--</option>}
                  {(field.suggestedOptions ?? []).map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                {(field.suggestedOptions ?? []).length === 0 && field.key === "connector_instance_id" && (
                  <p className="text-[11px] text-muted-foreground">
                    No connected instance yet — connect one in <Link to="/connectors" className="underline">Connectors</Link>
                  </p>
                )}
                {(field.suggestedOptions ?? []).length === 0 && field.key === "module" && (
                  <p className="text-[11px] text-muted-foreground">No modules available.</p>
                )}
              </>
            )}

            {field.kind === "array_text" && (
              <ArrayTextField control={control} name={field.key} field={field} errors={errors} />
            )}

            {field.kind === "array_object" && (
              <ArrayObjectField control={control} register={register} name={field.key} field={field} errors={errors} />
            )}

            {field.kind === "json_object" && (
              <JsonObjectField
                control={control}
                name={field.key}
                field={field}
                errors={errors}
                upstreamSuggestions={upstreamSuggestions}
              />
            )}

            {field.description && <p className="text-[11px] text-muted-foreground">{field.description}</p>}
            {field.kind !== "array_text" && field.kind !== "array_object" && field.kind !== "json_object" && errors[field.key] && (
              <p className="text-xs text-destructive">{String(errors[field.key]?.message)}</p>
            )}
          </div>
        ))}

        {nodeType.node_type === "whatsapp.ask_choice" && (
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-foreground">Options</label>
            <AskChoiceSourceField
              value={watch("source") as AskChoiceSource | undefined}
              onChange={(next) => setValue("source", next, { shouldDirty: true })}
              modules={modules}
            />
          </div>
        )}

        {(nodeType.node_type === "records.query" || nodeType.node_type === "records.upsert") && (
          <RecordModuleFields nodeType={nodeType.node_type} modules={modules} watch={watch} setValue={setValue} />
        )}

        <div className="mt-auto flex items-center gap-2 border-t border-border pt-3">
          <Button type="submit" size="sm" disabled={!isDirty}>
            Apply
          </Button>
          <Button type="button" variant="destructive" size="sm" onClick={onDelete}>
            Delete node
          </Button>
        </div>
      </form>
    </div>
  );
}
