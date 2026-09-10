import { TableCell, TableHead } from "@fusion-flow/ui";
import type { FieldDefinition } from "./types";

function sorted(definitions: FieldDefinition[]): FieldDefinition[] {
  return [...definitions].sort((a, b) => a.sort_order - b.sort_order);
}

/** Human-readable rendering of one custom field value for a list-table cell. */
export function formatCustomFieldValue(definition: FieldDefinition, value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (definition.field_type === "boolean") return value ? "Yes" : "No";
  if (definition.field_type === "multiselect" && Array.isArray(value)) return value.join(", ");
  if (definition.field_type === "date" && typeof value === "string") {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleDateString();
  }
  return String(value);
}

/**
 * One `<TableHead>` per field definition, sorted by `sort_order` — drop this
 * into a list table's header row (before the trailing "Actions" column) so
 * every custom field a business defines shows up as a real column, not just
 * in the create/edit form.
 */
export function DynamicCustomFieldsColumns({ definitions }: { definitions: FieldDefinition[] }) {
  return (
    <>
      {sorted(definitions).map((definition) => (
        <TableHead key={definition.id}>{definition.label}</TableHead>
      ))}
    </>
  );
}

/** The matching row of `<TableCell>`s for `DynamicCustomFieldsColumns`, reading from one item's `custom_fields`. */
export function DynamicCustomFieldsCells({
  definitions,
  values,
}: {
  definitions: FieldDefinition[];
  values: Record<string, unknown> | null | undefined;
}) {
  return (
    <>
      {sorted(definitions).map((definition) => (
        <TableCell key={definition.id} className="text-sm text-muted-foreground">
          {formatCustomFieldValue(definition, values?.[definition.key])}
        </TableCell>
      ))}
    </>
  );
}
