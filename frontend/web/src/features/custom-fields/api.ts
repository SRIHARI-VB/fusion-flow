import { apiClient } from "../../lib/api-client";
import type { ApplyTemplateResponse, CustomFieldEntityType, FieldDefinition, FieldTemplate } from "./types";

const BASE = "/api/v1/custom-fields";

export async function listFieldDefinitions(entityType: CustomFieldEntityType): Promise<FieldDefinition[]> {
  const { data } = await apiClient.get<FieldDefinition[]>(`${BASE}/definitions`, {
    params: { entity_type: entityType },
  });
  return data;
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
