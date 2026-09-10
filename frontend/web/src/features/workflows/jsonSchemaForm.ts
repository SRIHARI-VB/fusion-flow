import { z } from "zod";
import type { JsonSchema, JsonSchemaProperty } from "./types";

/**
 * Turns one node type's `config_schema` (raw JSON Schema, as produced by
 * `pydantic.BaseModel.model_json_schema()` on the backend) into enough
 * structure to render + validate a dynamic form with React Hook Form +
 * Zod — the "reuse the dynamic-form approach conceptually" instruction,
 * applied to node config instead of custom fields
 * (see `features/custom-fields/DynamicCustomFieldsFields.tsx` for the
 * sibling implementation this one is modeled after).
 *
 * This is a pragmatic subset of JSON Schema, not a general compiler: it
 * covers what pydantic actually emits for the node config models in this
 * codebase (string/number/integer/boolean, `enum`, nullable-via-`anyOf`,
 * `required`, and - added for Phase 5's WhatsApp buttons/list-rows/
 * contacts fields - `array` of a primitive or of a nested `BaseModel`,
 * resolved through pydantic's `$ref`/`$defs` indirection). A field shape
 * it doesn't recognize falls back to a plain text input.
 */

export type FieldKind = "text" | "number" | "boolean" | "select" | "array_text" | "array_object";

export interface ResolvedField {
  key: string;
  kind: FieldKind;
  label: string;
  description?: string;
  required: boolean;
  options?: string[];
  default?: unknown;
  /** Only set when `kind === "array_object"` - the sub-fields of one
   * array item, resolved the same recursive way as top-level fields, so
   * a sub-field that is itself an array-of-objects (e.g. an interactive
   * list's `sections[].rows`) renders correctly too. */
  itemFields?: ResolvedField[];
}

function baseType(prop: JsonSchemaProperty): string | undefined {
  if (prop.type && prop.type !== "null") return prop.type;
  const nonNull = prop.anyOf?.find((s) => s.type && s.type !== "null");
  return nonNull?.type;
}

/** Resolves a pydantic `"#/$defs/SomeModel"` ref against the top-level
 * schema's `$defs` map. Returns undefined for anything else (external
 * refs, malformed refs) - callers treat that as "couldn't resolve,
 * fall back to a simpler field kind" rather than throwing. */
function resolveRef(schema: JsonSchema, ref: string): JsonSchemaProperty | undefined {
  const match = /^#\/\$defs\/(.+)$/.exec(ref);
  if (!match) return undefined;
  return schema.$defs?.[match[1]];
}

function resolveItemsSchema(schema: JsonSchema, items: JsonSchemaProperty | undefined): JsonSchemaProperty | undefined {
  if (!items) return undefined;
  if (items.$ref) return resolveRef(schema, items.$ref);
  return items;
}

function fieldKind(schema: JsonSchema, prop: JsonSchemaProperty): FieldKind {
  if (prop.enum && prop.enum.length > 0) return "select";
  const type = baseType(prop);
  if (type === "boolean") return "boolean";
  if (type === "integer" || type === "number") return "number";
  if (type === "array") {
    const itemSchema = resolveItemsSchema(schema, prop.items);
    return itemSchema?.properties ? "array_object" : "array_text";
  }
  return "text";
}

function resolveField(schema: JsonSchema, key: string, prop: JsonSchemaProperty, requiredSet: Set<string>): ResolvedField {
  const kind = fieldKind(schema, prop);
  const field: ResolvedField = {
    key,
    kind,
    label: prop.title ?? key,
    description: prop.description,
    required: requiredSet.has(key),
    options: prop.enum,
    default: prop.default,
  };
  if (kind === "array_object") {
    const itemSchema = resolveItemsSchema(schema, prop.items);
    if (itemSchema?.properties) {
      const subRequired = new Set(itemSchema.required ?? []);
      field.itemFields = Object.entries(itemSchema.properties).map(([subKey, subProp]) =>
        resolveField(schema, subKey, subProp, subRequired),
      );
    }
  }
  return field;
}

export function resolveFields(schema: JsonSchema): ResolvedField[] {
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([key, prop]) => resolveField(schema, key, prop, required));
}

function zodForField(field: ResolvedField): z.ZodTypeAny {
  switch (field.kind) {
    case "boolean":
      return z.boolean();
    case "number":
      return field.required ? z.coerce.number() : z.coerce.number().optional();
    case "array_text": {
      let arr: z.ZodTypeAny = z.array(z.string());
      if (field.required) arr = (arr as z.ZodArray<z.ZodString>).min(1, `${field.label} requires at least one item`);
      return arr;
    }
    case "array_object": {
      const subShape: Record<string, z.ZodTypeAny> = {};
      for (const sub of field.itemFields ?? []) {
        subShape[sub.key] = zodForField(sub);
      }
      let arr: z.ZodTypeAny = z.array(z.object(subShape).passthrough());
      if (field.required) arr = (arr as z.ZodArray<z.ZodTypeAny>).min(1, `${field.label} requires at least one item`);
      return arr;
    }
    case "select":
    case "text":
    default: {
      let zodField: z.ZodTypeAny = z.string();
      if (field.required) zodField = (zodField as z.ZodString).min(1, `${field.label} is required`);
      return zodField;
    }
  }
}

/** Builds a `z.object(...)` shape from the resolved fields — required
 * fields must be non-empty; everything else is optional/nullable
 * (arrays are optional-only, never nullable - an empty array, not
 * `null`, is the "nothing entered yet" value `useFieldArray` expects). */
export function buildZodSchema(schema: JsonSchema): z.ZodTypeAny {
  const fields = resolveFields(schema);
  const shape: Record<string, z.ZodTypeAny> = {};

  for (const field of fields) {
    let zodField = zodForField(field);
    const isArray = field.kind === "array_text" || field.kind === "array_object";
    if (!field.required && field.kind !== "number" && !isArray) {
      zodField = zodField.optional().nullable();
    } else if (!field.required && isArray) {
      zodField = zodField.optional();
    }
    shape[field.key] = zodField;
  }

  return z.object(shape).passthrough();
}

function defaultForField(field: ResolvedField, existing: unknown): unknown {
  if (existing !== undefined) return existing;
  if (field.default !== undefined) return field.default;
  if (field.kind === "boolean") return false;
  if (field.kind === "array_text" || field.kind === "array_object") return [];
  return "";
}

/** Default form values: existing config wins, falling back to the
 * schema's own defaults, falling back to a kind-appropriate empty value.
 * For `array_object`, each existing row's own sub-fields are defaulted
 * the same recursive way, so a partially-filled saved row doesn't lose
 * its own defaults. */
export function buildDefaultValues(
  schema: JsonSchema,
  config: Record<string, unknown>,
): Record<string, unknown> {
  const fields = resolveFields(schema);
  const values: Record<string, unknown> = {};
  for (const field of fields) {
    if (field.kind === "array_object" && Array.isArray(config[field.key])) {
      values[field.key] = (config[field.key] as Array<Record<string, unknown>>).map((row) => {
        const rowValues: Record<string, unknown> = {};
        for (const sub of field.itemFields ?? []) {
          rowValues[sub.key] = defaultForField(sub, row[sub.key]);
        }
        return rowValues;
      });
    } else {
      values[field.key] = defaultForField(field, config[field.key]);
    }
  }
  return values;
}
