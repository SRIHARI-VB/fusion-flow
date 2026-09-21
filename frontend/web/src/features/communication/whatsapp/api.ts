import { apiClient } from "../../../lib/api-client";

/**
 * Talks to the predefined-automations routes, scoped to WhatsApp
 * (`connector_type_key=whatsapp`) - see
 * `backend/src/fusionflow/modules/predefined_automations` (router not
 * included in this feature's file list, spec'd in the task description
 * this feature was built from). Every function here maps 1:1 to one
 * backend endpoint, mirroring `features/connectors/api.ts`'s convention.
 */

export type WhatsAppAutomationMatchingMethod = "exact" | "contains" | "starts_with" | "ends_with";

export interface WhatsAppAppointmentBookingConfig {
  trigger_keywords: string[];
  matching_method: WhatsAppAutomationMatchingMethod;
  service_name: string;
  duration_minutes: number;
  confirmation_message: string | null;
}

export interface WhatsAppAutomation {
  id: string;
  connector_instance_id: string;
  automation_type: string;
  workflow_id: string | null;
  config: WhatsAppAppointmentBookingConfig;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateWhatsAppAutomationPayload {
  connector_instance_id: string;
  automation_type: "whatsapp.appointment_booking";
  name: string;
  config: WhatsAppAppointmentBookingConfig;
}

export async function fetchWhatsAppAutomations(): Promise<WhatsAppAutomation[]> {
  const { data } = await apiClient.get<WhatsAppAutomation[]>("/api/v1/predefined-automations", {
    params: { connector_type_key: "whatsapp" },
  });
  return data;
}

export async function createWhatsAppAutomation(
  payload: CreateWhatsAppAutomationPayload,
): Promise<WhatsAppAutomation> {
  const { data } = await apiClient.post<WhatsAppAutomation>("/api/v1/predefined-automations", payload);
  return data;
}

export async function updateWhatsAppAutomation(
  id: string,
  config: WhatsAppAppointmentBookingConfig,
): Promise<WhatsAppAutomation> {
  const { data } = await apiClient.patch<WhatsAppAutomation>(`/api/v1/predefined-automations/${id}`, {
    config,
  });
  return data;
}

export async function setWhatsAppAutomationActive(id: string, isActive: boolean): Promise<WhatsAppAutomation> {
  const { data } = await apiClient.post<WhatsAppAutomation>(`/api/v1/predefined-automations/${id}/active`, {
    is_active: isActive,
  });
  return data;
}

export async function deleteWhatsAppAutomation(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/predefined-automations/${id}`);
}
