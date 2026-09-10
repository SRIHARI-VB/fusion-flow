import type { UseFormRegister } from "react-hook-form";
import { Input } from "@fusion-flow/ui";
import type { FieldDefinition } from "./types";

interface DynamicCustomFieldsFieldsProps {
  definitions: FieldDefinition[];
  /**
   * The *parent* page's own `useForm()` register function. Every input here
   * registers under the dot-path `custom_fields.<key>`, which is how
   * react-hook-form nests plain object values on submit — so
   * `handleSubmit(onSubmit)` hands `onSubmit` a `custom_fields: {...}` object
   * for free, with no separate form state to merge in.
   */
  register: UseFormRegister<any>;
  /** `formState.errors` from the same form instance, for inline messages. */
  errors?: Record<string, any>;
}

const selectClassName =
  "flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50";

const textareaClassName =
  "flex w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground " +
  "placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * Renders one input per `FieldDefinition`, built at runtime from whatever
 * the tenant currently has configured for an entity_type — this is the
 * "custom fields render dynamically" requirement. All the supported
 * field_types (text/number/boolean/select/multiselect/date/richtext) map to
 * plain HTML inputs; richtext is a plain textarea, per the phase-1 scope.
 */
export function DynamicCustomFieldsFields({ definitions, register, errors }: DynamicCustomFieldsFieldsProps) {
  if (definitions.length === 0) return null;

  return (
    <>
      {definitions
        .slice()
        .sort((a, b) => a.sort_order - b.sort_order)
        .map((definition) => {
          const name = `custom_fields.${definition.key}`;
          const message = errors?.custom_fields?.[definition.key]?.message as string | undefined;

          return (
            <div key={definition.id} className="flex flex-col gap-1.5">
              <label htmlFor={name} className="text-sm font-medium">
                {definition.label}
                {definition.required && <span className="text-destructive"> *</span>}
              </label>
              {renderInput(definition, name, register)}
              {message && <p className="text-xs text-destructive">{message}</p>}
            </div>
          );
        })}
    </>
  );
}

function renderInput(definition: FieldDefinition, name: string, register: UseFormRegister<any>) {
  const options = (definition.options ?? []).map((opt) =>
    typeof opt === "object" && opt !== null ? (opt as { value?: unknown; label?: unknown }) : { value: opt, label: opt },
  );
  // `definition.required` (set on the field's definition, not per-item) must
  // actually be enforced here, not just shown as a "*" label - previously
  // every input registered with no validation rule at all, so a "required"
  // custom field could be silently left blank on every create/edit submit.
  const requiredMessage = definition.required ? `${definition.label} is required` : false;

  switch (definition.field_type) {
    case "boolean":
      return (
        <input
          id={name}
          type="checkbox"
          className="h-4 w-4 rounded border-input"
          {...register(name, { required: requiredMessage })}
        />
      );

    case "number":
      return (
        <Input
          id={name}
          type="number"
          step="any"
          {...register(name, { valueAsNumber: true, required: requiredMessage })}
        />
      );

    case "date":
      return <Input id={name} type="date" {...register(name, { required: requiredMessage })} />;

    case "richtext":
      return (
        <textarea
          id={name}
          rows={4}
          className={textareaClassName}
          {...register(name, { required: requiredMessage })}
        />
      );

    case "select":
      return (
        <select
          id={name}
          defaultValue=""
          className={selectClassName}
          {...register(name, { required: requiredMessage })}
        >
          <option value="" disabled>
            Select...
          </option>
          {options.map((opt) => (
            <option key={String(opt.value)} value={String(opt.value)}>
              {String(opt.label ?? opt.value)}
            </option>
          ))}
        </select>
      );

    case "multiselect":
      return (
        <select
          id={name}
          multiple
          className={`${selectClassName} min-h-[6rem]`}
          {...register(name, { required: requiredMessage })}
        >
          {options.map((opt) => (
            <option key={String(opt.value)} value={String(opt.value)}>
              {String(opt.label ?? opt.value)}
            </option>
          ))}
        </select>
      );

    case "text":
    default:
      return <Input id={name} {...register(name, { required: requiredMessage })} />;
  }
}
