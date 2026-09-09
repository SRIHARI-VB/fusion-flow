import { apiClient } from "../../lib/api-client";
import type {
  ApplyTemplateResponse,
  CustomFieldEntityType,
  FieldDefinition,
  FieldDefinitionCreateInput,
  FieldDefinitionUpdateInput,
  FieldTemplate,
} from "./types";

const BASE = "/api/v1/custom-fields";

export async function listFieldDefinitions(entityType: CustomFieldEntityType): Promise<FieldDefinition[]> {
  const { data } = await apiClient.get<FieldDefinition[]>(`${BASE}/definitions`, {
    params: { entity_type: entityType },
  });
  return data;
}

export async function createFieldDefinition(payload: FieldDefinitionCreateInput): Promise<FieldDefinition> {
  const { data } = await apiClient.post<FieldDefinition>(`${BASE}/definitions`, payload);
  return data;
}

export async function updateFieldDefinition(
  id: string,
  payload: FieldDefinitionUpdateInput,
): Promise<FieldDefinition> {
  const { data } = await apiClient.patch<FieldDefinition>(`${BASE}/definitions/${id}`, payload);
  return data;
}

export async function deleteFieldDefinition(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/definitions/${id}`);
}

export async function listFieldTemplates(params?: {
  vertical?: string;
  entity_type?: CustomFieldEntityType;
}): Promise<FieldTemplate[]> {
  const { data } = await apiClient.get<FieldTemplate[]>(`${BASE}/templates`, { params });
  return data;
}

export async function applyFieldTemplate(templateId: string): Promise<ApplyTemplateResponse> {
  const { data } = await apiClient.post<ApplyTemplateResponse>(`${BASE}/templates/${templateId}/apply`);
  return data;
}
