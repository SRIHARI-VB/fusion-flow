import { apiClient } from "../../../lib/api-client";

/**
 * Talks to the WhatsApp template catalog routes
 * (`backend/src/fusionflow/modules/connectors/whatsapp/router.py`) - what
 * `WhatsAppSettingsPanel.tsx` reads/writes and what the
 * `whatsapp.send_template` workflow node's config drawer will eventually
 * read from for its picker.
 */

export type WhatsAppTemplateCategory = "marketing" | "utility" | "authentication";
export type WhatsAppTemplateStatus = "approved" | "pending" | "rejected";

export interface WhatsAppTemplate {
  id: string;
  connector_instance_id: string;
  name: string;
  language: string;
  category: WhatsAppTemplateCategory;
  status: WhatsAppTemplateStatus;
  components: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface WhatsAppTemplateCreateRequest {
  name: string;
  language: string;
  category: WhatsAppTemplateCategory;
  status?: WhatsAppTemplateStatus;
  components?: Record<string, unknown>;
}

export async function fetchWhatsAppTemplates(instanceId: string): Promise<WhatsAppTemplate[]> {
  const { data } = await apiClient.get<WhatsAppTemplate[]>(`/api/v1/connectors/${instanceId}/whatsapp/templates`);
  return data;
}

export async function createWhatsAppTemplate(
  instanceId: string,
  payload: WhatsAppTemplateCreateRequest,
): Promise<WhatsAppTemplate> {
  const { data } = await apiClient.post<WhatsAppTemplate>(
    `/api/v1/connectors/${instanceId}/whatsapp/templates`,
    payload,
  );
  return data;
}

export async function deleteWhatsAppTemplate(instanceId: string, templateId: string): Promise<void> {
  await apiClient.delete(`/api/v1/connectors/${instanceId}/whatsapp/templates/${templateId}`);
}

export async function syncWhatsAppTemplates(instanceId: string): Promise<WhatsAppTemplate[]> {
  const { data } = await apiClient.post<WhatsAppTemplate[]>(
    `/api/v1/connectors/${instanceId}/whatsapp/templates/sync`,
  );
  return data;
}
