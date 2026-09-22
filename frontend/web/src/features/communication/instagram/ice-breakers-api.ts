import { apiClient } from "../../../lib/api-client";

/**
 * Talks to `/api/v1/connectors/{instance_id}/instagram/ice-breakers` -
 * the Instagram Messaging "welcome menu" a customer sees the first time
 * they open a new DM conversation with this account. Deliberately kept
 * separate from `api.ts` (which is scoped to `PredefinedAutomation`
 * CRUD): ice breakers are a one-time-per-account settings blob, not a
 * workflow/automation, mirroring how the backend router is mounted
 * separately (see `backend/src/fusionflow/modules/connectors/instagram/router.py`).
 */

export interface IceBreakerQuestion {
  question: string;
  payload: string;
}

export async function fetchIceBreakers(instanceId: string): Promise<IceBreakerQuestion[]> {
  const { data } = await apiClient.get<IceBreakerQuestion[]>(
    `/api/v1/connectors/${instanceId}/instagram/ice-breakers`,
  );
  return data;
}

export async function saveIceBreakers(
  instanceId: string,
  questions: IceBreakerQuestion[],
): Promise<IceBreakerQuestion[]> {
  const { data } = await apiClient.put<IceBreakerQuestion[]>(
    `/api/v1/connectors/${instanceId}/instagram/ice-breakers`,
    { questions },
  );
  return data;
}
