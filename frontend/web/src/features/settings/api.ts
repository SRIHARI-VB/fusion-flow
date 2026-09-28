import type { Business } from "@fusion-flow/ts-types";
import { apiClient } from "../../lib/api-client";
import type { Member } from "./types";

export interface BusinessSettingsUpdateInput {
  name?: string;
  vertical?: string;
  messaging_paused?: boolean;
}

/** `PATCH /api/v1/businesses/{id}` — owner/admin only, must match the active tenant. */
export async function updateBusinessSettings(
  businessId: string,
  payload: BusinessSettingsUpdateInput,
): Promise<Business> {
  const { data } = await apiClient.patch<Business>(`/api/v1/businesses/${businessId}`, payload);
  return data;
}

/** `GET /api/v1/businesses/{id}/members` — owner/admin only, must match the active tenant. */
export async function fetchMembers(businessId: string): Promise<Member[]> {
  const { data } = await apiClient.get<Member[]>(`/api/v1/businesses/${businessId}/members`);
  return data;
}

/** `PATCH /api/v1/businesses/{id}/members/{membershipId}` — owner/admin only,
 * currently just the doctor flag (see `Member.is_doctor`). */
export async function updateMemberIsDoctor(
  businessId: string,
  membershipId: string,
  isDoctor: boolean,
): Promise<Member> {
  const { data } = await apiClient.patch<Member>(
    `/api/v1/businesses/${businessId}/members/${membershipId}`,
    { is_doctor: isDoctor },
  );
  return data;
}
