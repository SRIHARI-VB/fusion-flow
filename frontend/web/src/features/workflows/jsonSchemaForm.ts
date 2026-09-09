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
 * `required`). A field type it doesn't recognize falls back to a plain
 * text input.
 */

export type FieldKind = "text" | "number" | "boolean" | "select";

export interface ResolvedField {
  key: string;
  kind: FieldKind;
  label: string;
  description?: string;
  required: boolean;
  options?: string[];
  default?: unknown;
}

function baseType(prop: JsonSchemaProperty): string | undefined {
  if (prop.type && prop.type !== "null") return prop.type;
  const nonNull = prop.anyOf?.find((s) => s.type && s.type !== "null");
  return nonNull?.type;
}

function fieldKind(prop: JsonSchemaProperty): FieldKind {
  if (prop.enum && prop.enum.length > 0) return "select";
  const type = baseType(prop);
  if (type === "boolean") return "boolean";
  if (type === "integer" || type === "number") return "number";
  return "text";
}

export function resolveFields(schema: JsonSchema): ResolvedField[] {
  const required = new Set(schema.required ?? []);
  return Object.entries(schema.properties ?? {}).map(([key, prop]) => ({
    key,
    kind: fieldKind(prop),
    label: prop.title ?? key,
    description: prop.description,
    required: required.has(key),
    options: prop.enum,
    default: prop.default,
  }));
}

/** Builds a `z.object(...)` shape from the resolved fields — required
 * fields must be non-empty; everything else is optional/nullable. */
export function buildZodSchema(schema: JsonSchema): z.ZodTypeAny {
  const fields = resolveFields(schema);
  const shape: Record<string, z.ZodTypeAny> = {};

  for (const field of fields) {
    let zodField: z.ZodTypeAny;
    switch (field.kind) {
      case "boolean":
        zodField = z.boolean();
        break;
      case "number":
        zodField = field.required ? z.coerce.number() : z.coerce.number().optional();
        break;
      case "select":
      case "text":
      default:
        zodField = z.string();
        if (field.required) zodField = (zodField as z.ZodString).min(1, `${field.label} is required`);
        break;
    }
    if (!field.required && field.kind !== "number") {
      zodField = zodField.optional().nullable();
    }
    shape[field.key] = zodField;
  }

  return z.object(shape).passthrough();
}

/** Default form values: existing config wins, falling back to the
 * schema's own defaults, falling back to a kind-appropriate empty value. */
export function buildDefaultValues(
  schema: JsonSchema,
  config: Record<string, unknown>,
): Record<string, unknown> {
  const fields = resolveFields(schema);
  const values: Record<string, unknown> = {};
  for (const field of fields) {
    if (config[field.key] !== undefined) {
      values[field.key] = config[field.key];
    } else if (field.default !== undefined) {
      values[field.key] = field.default;
    } else {
      values[field.key] = field.kind === "boolean" ? false : "";
    }
  }
  return values;
}
