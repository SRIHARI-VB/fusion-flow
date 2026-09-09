import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { X } from "lucide-react";
import { Button, Input } from "@fusion-flow/ui";
import type { NodeType } from "../types";
import { buildDefaultValues, buildZodSchema, resolveFields } from "../jsonSchemaForm";

/**
 * Per-node config drawer — a dynamic form built from the selected node's
 * `config_schema` (React Hook Form + Zod, same conceptual approach as
 * `features/custom-fields/DynamicCustomFieldsFields.tsx`). Replaces the
 * palette in the same right-hand column while a node is selected.
 */

interface NodeConfigDrawerProps {
  nodeId: string;
  nodeType: NodeType;
  label: string;
  config: Record<string, unknown>;
  onLabelChange: (label: string) => void;
  onSave: (config: Record<string, unknown>) => void;
  onClose: () => void;
  onDelete: () => void;
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
}: NodeConfigDrawerProps) {
  const fields = resolveFields(nodeType.config_schema);
  const schema = buildZodSchema(nodeType.config_schema);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<Record<string, unknown>>({
    resolver: zodResolver(schema as never),
    defaultValues: buildDefaultValues(nodeType.config_schema, config),
  });

  // Re-hydrate the form whenever the selected node changes (nodeId is the
  // stable identity signal here — `config` is a new object reference on
  // every render otherwise).
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    reset(buildDefaultValues(nodeType.config_schema, config));
  }, [nodeId]);

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
            <label htmlFor={field.key} className="text-xs font-medium text-foreground">
              {field.label}
              {field.required && <span className="text-destructive"> *</span>}
            </label>

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

            {field.description && <p className="text-[11px] text-muted-foreground">{field.description}</p>}
            {errors[field.key] && (
              <p className="text-xs text-destructive">{String(errors[field.key]?.message)}</p>
            )}
          </div>
        ))}

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
