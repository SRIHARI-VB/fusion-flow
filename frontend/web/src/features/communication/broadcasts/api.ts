import { apiClient } from "../../../lib/api-client";
import type { BroadcastCampaign, CreateBroadcastCampaignPayload } from "./types";

/**
 * Talks to the broadcast-campaign routes
 * (`backend/src/fusionflow/modules/.../broadcast_campaigns` router). Every
 * function here maps 1:1 to one backend endpoint, mirroring the calling
 * convention in `frontend/web/src/features/connectors/api.ts`.
 */

export async function fetchCampaigns(): Promise<BroadcastCampaign[]> {
  const { data } = await apiClient.get<BroadcastCampaign[]>("/api/v1/broadcast-campaigns");
  return data;
}

export async function createCampaign(payload: CreateBroadcastCampaignPayload): Promise<BroadcastCampaign> {
  const { data } = await apiClient.post<BroadcastCampaign>("/api/v1/broadcast-campaigns", payload);
  return data;
}

export async function getCampaign(id: string): Promise<BroadcastCampaign> {
  const { data } = await apiClient.get<BroadcastCampaign>(`/api/v1/broadcast-campaigns/${id}`);
  return data;
}

export async function setCampaignActive(id: string, isActive: boolean): Promise<BroadcastCampaign> {
  const { data } = await apiClient.post<BroadcastCampaign>(`/api/v1/broadcast-campaigns/${id}/active`, {
    is_active: isActive,
  });
  return data;
}

export async function deleteCampaign(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/broadcast-campaigns/${id}`);
}
