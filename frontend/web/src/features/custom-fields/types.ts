/** Mirrors `fusionflow.modules.custom_fields.schemas` on the backend. */

export type CustomFieldEntityType = "product" | "service" | "coupon" | "offer";

export type CustomFieldType =
  | "text"
  | "number"
  | "boolean"
  | "select"
  | "multiselect"
  | "date"
  | "richtext";

export interface FieldDefinition {
  id: string;
  entity_type: CustomFieldEntityType;
  key: string;
  label: string;
  field_type: CustomFieldType;
  options: unknown[] | null;
  required: boolean;
  sort_order: number;
  source_template_id: string | null;
  created_at: string;
}

export interface FieldDefinitionCreateInput {
  entity_type: CustomFieldEntityType;
  key: string;
  label: string;
  field_type: CustomFieldType;
  options?: unknown[] | null;
  required?: boolean;
  sort_order?: number;
}

export interface FieldDefinitionUpdateInput {
  label?: string;
  options?: unknown[] | null;
  required?: boolean;
  sort_order?: number;
}

export interface FieldTemplateFieldSpec {
  key: string;
  label: string;
  field_type: CustomFieldType;
  options: unknown[] | null;
  required: boolean;
  sort_order: number;
}

export interface FieldTemplate {
  id: string;
  vertical: string;
  entity_type: CustomFieldEntityType;
  is_global: boolean;
  name: string;
  version: number;
  fields: FieldTemplateFieldSpec[];
  created_at: string;
}

export interface ApplyTemplateResponse {
  created: FieldDefinition[];
  skipped_existing_keys: string[];
}

/** Loose shape used to build/submit a dynamic `custom_fields` value at runtime. */
export type CustomFieldsValue = Record<string, unknown>;
