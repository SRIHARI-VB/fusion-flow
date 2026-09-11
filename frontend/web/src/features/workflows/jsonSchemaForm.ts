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

export type FieldKind =
  | "text"
  | "textarea"
  | "number"
  | "boolean"
  | "select"
  | "array_text"
  | "array_object"
  | "json_object"
  | "suggested_select";

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
  /** Only set when `kind === "suggested_select"` - the tenant-specific
   * `{value, label}` options computed server-side (`NodeType.field_suggestions`),
   * e.g. connected connector instances or granted modules. */
  suggestedOptions?: { value: string; label: string }[];
}

/** Per-config-field precomputed option lists, as returned by the backend
 * on `NodeType.field_suggestions` - keyed by config field name. */
export type FieldSuggestions = Record<string, { value: string; label: string }[]> | null | undefined;

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
  if (type === "object") {
    // A pydantic `dict[str, Any]` field (e.g. `module.list`'s `filters`,
    // `connector.action`'s `params`) has no fixed `properties` - resolve a
    // `$ref` first (mirrors `resolveItemsSchema`'s treatment of arrays)
    // since a dict-shaped def can also be expressed indirectly.
    const resolved = prop.$ref ? resolveRef(schema, prop.$ref) : prop;
    if (!resolved?.properties) return "json_object";
  }
  // Backend hint (`Field(json_schema_extra={"format": "textarea"})`) for a
  // plain string field that holds multi-line message/body content (a
  // WhatsApp body, a question being asked, ...) rather than a short
  // single-line value - checked last, after every other shape-based kind,
  // so it only ever applies to what would otherwise be a plain "text" field.
  if (prop.format === "textarea") return "textarea";
  return "text";
}

function resolveField(
  schema: JsonSchema,
  key: string,
  prop: JsonSchemaProperty,
  requiredSet: Set<string>,
  fieldSuggestions?: FieldSuggestions,
): ResolvedField {
  const suggested = fieldSuggestions?.[key];
  const kind = suggested ? "suggested_select" : fieldKind(schema, prop);
  const field: ResolvedField = {
    key,
    kind,
    label: prop.title ?? key,
    description: prop.description,
    required: requiredSet.has(key),
    options: prop.enum,
    default: prop.default,
  };
  if (suggested) field.suggestedOptions = suggested;
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

export function resolveFields(schema: JsonSchema, fieldSuggestions?: FieldSuggestions): ResolvedField[] {
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([key, prop]) =>
    resolveField(schema, key, prop, required, fieldSuggestions),
  );
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
    case "json_object":
      return z.record(z.string(), z.unknown());
    case "select":
    case "suggested_select":
    case "text":
    case "textarea":
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
export function buildZodSchema(schema: JsonSchema, fieldSuggestions?: FieldSuggestions): z.ZodTypeAny {
  const fields = resolveFields(schema, fieldSuggestions);
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
  if (field.kind === "json_object") return {};
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
  fieldSuggestions?: FieldSuggestions,
): Record<string, unknown> {
  const fields = resolveFields(schema, fieldSuggestions);
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

/** Walks a node type's `output_schema` (same JSON-Schema-lite shape as
 * `config_schema`, resolved through `$ref`/`$defs` the same way) to build
 * the "insert variable" picker's options - one `{path, label}` per leaf
 * key, `path` being the dotted reference to append inside `{{...}}`
 * (`prefix` is the upstream node's own graph id) and `label` a
 * human-readable "›"-joined breadcrumb. Returns `[]` for a `null`/absent
 * schema (most node types don't declare one yet); for a schema with no
 * `properties` at all, returns the bare node reference itself - still a
 * useful insertion (`{{node_id}}`) even with no known sub-shape. */
export function flattenOutputPaths(
  schema: JsonSchema | null | undefined,
  prefix: string,
): { path: string; label: string }[] {
  if (!schema) return [];
  if (!schema.properties || Object.keys(schema.properties).length === 0) {
    return [{ path: prefix, label: prefix }];
  }

  function walk(properties: Record<string, JsonSchemaProperty>, path: string, label: string): { path: string; label: string }[] {
    const results: { path: string; label: string }[] = [];
    for (const [key, prop] of Object.entries(properties)) {
      const resolved = prop.$ref ? resolveRef(schema!, prop.$ref) : prop;
      const nextPath = `${path}.${key}`;
      const nextLabel = `${label} › ${prop.title ?? key}`;
      if (resolved?.properties) {
        results.push(...walk(resolved.properties, nextPath, nextLabel));
      } else {
        results.push({ path: nextPath, label: nextLabel });
      }
    }
    return results;
  }

  return walk(schema.properties, prefix, prefix);
}
