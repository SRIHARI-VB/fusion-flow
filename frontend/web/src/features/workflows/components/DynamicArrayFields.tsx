import { useController, useFieldArray, type Control, type FieldErrors, type UseFormRegister } from "react-hook-form";
import { Plus, Trash2 } from "lucide-react";
import { Button, Input } from "@fusion-flow/ui";
import type { ResolvedField } from "../jsonSchemaForm";

/**
 * Renders a repeatable field for `array_text`/`array_object`-kind
 * `ResolvedField`s (see `jsonSchemaForm.ts`) - the piece that makes
 * WhatsApp's buttons/list-rows/contacts fields (and any future
 * integration's own repeatable field) usable in the builder instead of
 * only editable as raw JSON. `ArrayObjectField` recurses for a sub-field
 * that is itself array-of-objects (e.g. an interactive list's
 * `sections[].rows`), so nesting depth isn't hardcoded to WhatsApp's
 * specific shapes.
 *
 * `array_text` is deliberately NOT built on `useFieldArray` - that hook
 * requires each array item to be an object (it merges in its own
 * synthetic `id` key per row), so a plain `string[]` doesn't work with
 * it. `useController` on the whole array value instead, treating it as
 * one controlled field the component manages its own add/remove/edit
 * logic for, sidesteps that limitation entirely.
 */

interface ArrayFieldProps {
  control: Control<Record<string, unknown>>;
  register: UseFormRegister<Record<string, unknown>>;
  name: string;
  field: ResolvedField;
  errors: FieldErrors;
}

function errorAt(errors: FieldErrors, path: string): string | undefined {
  const parts = path.split(".");
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let current: any = errors;
  for (const part of parts) {
    if (current == null) return undefined;
    current = current[part];
  }
  return current?.message ? String(current.message) : undefined;
}

export function ArrayTextField({ control, name, field, errors }: Omit<ArrayFieldProps, "register">) {
  const { field: controllerField } = useController({ control, name: name as never, defaultValue: [] as never });
  const values: string[] = Array.isArray(controllerField.value) ? (controllerField.value as string[]) : [];

  function updateAt(index: number, value: string) {
    const next = [...values];
    next[index] = value;
    controllerField.onChange(next);
  }

  return (
    <div className="flex flex-col gap-2">
      {values.map((value, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <Input
            value={value}
            onChange={(e) => updateAt(index, e.target.value)}
            placeholder={`${field.label} ${index + 1}`}
          />
          <button
            type="button"
            aria-label="Remove item"
            className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
            onClick={() => controllerField.onChange(values.filter((_, i) => i !== index))}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => controllerField.onChange([...values, ""])}>
        <Plus className="h-3.5 w-3.5" />
        Add {field.label.toLowerCase()}
      </Button>
      {errorAt(errors, name) && <p className="text-xs text-destructive">{errorAt(errors, name)}</p>}
    </div>
  );
}

function emptyRowFor(field: ResolvedField): Record<string, unknown> {
  const row: Record<string, unknown> = {};
  for (const sub of field.itemFields ?? []) {
    row[sub.key] = sub.kind === "array_text" || sub.kind === "array_object" ? [] : sub.kind === "boolean" ? false : "";
  }
  return row;
}

export function ArrayObjectField({ control, register, name, field, errors }: ArrayFieldProps) {
  const { fields: rows, append, remove } = useFieldArray({ control, name: name as never });

  return (
    <div className="flex flex-col gap-2">
      {rows.map((row, index) => (
        <div key={row.id} className="flex flex-col gap-2 rounded-md border border-border p-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {field.label} {index + 1}
            </span>
            <button
              type="button"
              aria-label="Remove row"
              className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
              onClick={() => remove(index)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>

          {(field.itemFields ?? []).map((sub) => {
            const subName = `${name}.${index}.${sub.key}`;
            if (sub.kind === "array_text") {
              return <ArrayTextField key={sub.key} control={control} name={subName} field={sub} errors={errors} />;
            }
            if (sub.kind === "array_object") {
              return (
                <ArrayObjectField
                  key={sub.key} control={control} register={register} name={subName} field={sub} errors={errors}
                />
              );
            }
            return (
              <div key={sub.key} className="flex flex-col gap-1">
                <label className="text-[11px] text-muted-foreground" htmlFor={subName}>
                  {sub.label}
                  {sub.required && <span className="text-destructive"> *</span>}
                </label>
                {sub.kind === "boolean" ? (
                  <input id={subName} type="checkbox" className="h-4 w-4" {...register(subName as never)} />
                ) : sub.kind === "select" ? (
                  <select
                    id={subName}
                    className="h-9 rounded-md border border-input bg-card px-2 text-sm"
                    {...register(subName as never)}
                  >
                    {!sub.required && <option value="">--</option>}
                    {(sub.options ?? []).map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input id={subName} type={sub.kind === "number" ? "number" : "text"} {...register(subName as never)} />
                )}
                {errorAt(errors, subName) && <p className="text-xs text-destructive">{errorAt(errors, subName)}</p>}
              </div>
            );
          })}
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={() => append(emptyRowFor(field) as never)}>
        <Plus className="h-3.5 w-3.5" />
        Add {field.label.toLowerCase()}
      </Button>
      {errorAt(errors, name) && <p className="text-xs text-destructive">{errorAt(errors, name)}</p>}
    </div>
  );
}
