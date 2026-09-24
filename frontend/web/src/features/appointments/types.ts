/** Mirrors `fusionflow.modules.business_objects.schemas` on the backend. */
import type { CustomFieldType, FieldDefinition } from "../custom-fields/types";

export interface ObjectType {
  id: string;
  key: string;
  name: string;
  icon: string | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ObjectFieldDefinition {
  id: string;
  object_type_id: string;
  key: string;
  label: string;
  field_type: CustomFieldType;
  options: unknown[] | null;
  required: boolean;
  sort_order: number;
  created_at: string;
}

export interface ObjectRecord {
  id: string;
  object_type_id: string;
  payload: Record<string, unknown>;
  customer_id: string | null;
  created_by_run_id: string | null;
  created_at: string;
  updated_at: string;
}

/**
 * Adapts a business-object field definition to the `FieldDefinition` shape
 * `DynamicCustomFieldsColumns`/`DynamicCustomFieldsCells` (from
 * `features/custom-fields`) expect. Those components were built around a
 * fixed module's `entity_type`-keyed field defs, but only ever read
 * `id`/`key`/`label`/`field_type`/`options`/`sort_order` off the definition -
 * `entity_type` and `source_template_id` are stubbed here purely to satisfy
 * the shared type, and are never read by either component.
 */
export function toDisplayFieldDefinition(field: ObjectFieldDefinition): FieldDefinition {
  return {
    id: field.id,
    entity_type: "offer",
    key: field.key,
    label: field.label,
    field_type: field.field_type,
    options: field.options,
    required: field.required,
    sort_order: field.sort_order,
    source_template_id: null,
    created_at: field.created_at,
  };
}
