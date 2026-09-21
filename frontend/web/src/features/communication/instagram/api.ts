import { apiClient } from "../../../lib/api-client";
import type { CreateInstagramAutomationPayload, InstagramAutomationConfig, PredefinedAutomation } from "./types";

/**
 * Talks to the generic predefined-automations routes
 * (`GET/POST /api/v1/predefined-automations`, `PATCH/DELETE
 * /api/v1/predefined-automations/{id}`, `POST .../{id}/active`), scoped
 * to Instagram's automation types ("Comment Automation" and
 * "DM Auto-Reply"). Mirrors `frontend/web/src/features/connectors/api.ts`'s
 * 1:1 endpoint mapping.
 */

export async function fetchInstagramAutomations(): Promise<PredefinedAutomation[]> {
  const { data } = await apiClient.get<PredefinedAutomation[]>("/api/v1/predefined-automations", {
    params: { connector_type_key: "instagram" },
  });
  return data;
}

export async function createInstagramAutomation(
  payload: CreateInstagramAutomationPayload,
): Promise<PredefinedAutomation> {
  const { data } = await apiClient.post<PredefinedAutomation>("/api/v1/predefined-automations", {
    connector_instance_id: payload.connector_instance_id,
    automation_type: payload.automation_type,
    name: payload.name,
    config: payload.config,
  });
  return data;
}

export async function updateInstagramAutomation(
  id: string,
  config: InstagramAutomationConfig,
): Promise<PredefinedAutomation> {
  const { data } = await apiClient.patch<PredefinedAutomation>(`/api/v1/predefined-automations/${id}`, { config });
  return data;
}

export async function setInstagramAutomationActive(id: string, isActive: boolean): Promise<PredefinedAutomation> {
  const { data } = await apiClient.post<PredefinedAutomation>(`/api/v1/predefined-automations/${id}/active`, {
    is_active: isActive,
  });
  return data;
}

export async function deleteInstagramAutomation(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/predefined-automations/${id}`);
}
