import type { JsonSchema, JsonSchemaProperty } from "./types";

/**
 * Turns one node type's `config_schema` (raw JSON Schema, as produced by
 * `pydantic.BaseModel.model_json_schema()` on the backend) into enough
 * structure to render every field directly inline on its card (see
 * `NodeInlineForm.tsx`) - no React Hook Form/Zod involved on this path
 * anymore; every field commits straight into `data.config` via plain
 * `value`/`onChange` (see `DraftFields.tsx` for why free-text fields buffer
 * locally before committing).
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
  | "suggested_select"
  | "recipient"
  | "auto_ref";

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
  /** Only set when `kind === "auto_ref"` - mirrors `JsonSchemaProperty.ref_suffix`,
   * the upstream output leaf key (e.g. `"recipients"`, `"message_id"`) this
   * field should auto-resolve a reference to - see `NodeInlineForm.tsx`'s
   * `"auto_ref"` render branch. */
  ref_suffix?: string;
  /** The backend's own declared `maxLength` (pydantic `Field(max_length=...)`),
   * e.g. a WhatsApp interactive button's 20-character title limit - surfaced
   * so a `"text"`/`"textarea"` input can enforce it natively and show a live
   * character counter instead of only failing at publish/send time.
   * `undefined` when the backend hasn't declared one - no counter is shown
   * in that case, since we shouldn't invent a limit the backend didn't set. */
  maxLength?: number;
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
  if (prop.format === "recipient") return "recipient";
  // Backend hint for a plain string field whose real value should be an
  // upstream reference (`{{node_id.<ref_suffix>}}`) the author almost
  // always wants auto-filled rather than typed by hand (e.g. `flow.loop`'s
  // `items_path`, `whatsapp.mark_as_read`'s `message_id`) - see
  // `NodeInlineForm.tsx`'s `"auto_ref"` render branch.
  if (prop.format === "auto_ref") return "auto_ref";
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
  if (prop.ref_suffix) field.ref_suffix = prop.ref_suffix;
  if (typeof prop.maxLength === "number") field.maxLength = prop.maxLength;
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
