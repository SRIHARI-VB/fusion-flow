import type { Business } from "@fusion-flow/ts-types";
import { apiClient } from "../../lib/api-client";

export interface BusinessUpdateInput {
  name?: string;
  vertical?: string;
  mark_onboarding_complete?: boolean;
}

/** `PATCH /api/v1/businesses/{id}` — owner/admin only, must match the active tenant. */
export async function updateBusiness(businessId: string, payload: BusinessUpdateInput): Promise<Business> {
  const { data } = await apiClient.patch<Business>(`/api/v1/businesses/${businessId}`, payload);
  return data;
}
