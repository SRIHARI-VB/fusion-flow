import { apiClient } from "../../../lib/api-client";
import type { QuickReply, QuickReplyPayload } from "./types";

/**
 * Talks to the quick-reply snippet routes
 * (`backend/src/fusionflow/modules/...` quick-replies router). Every
 * function here maps 1:1 to one backend endpoint, mirroring the
 * connectors feature's `api.ts` convention.
 */

export async function fetchQuickReplies(): Promise<QuickReply[]> {
  const { data } = await apiClient.get<QuickReply[]>("/api/v1/quick-replies");
  return data;
}

export async function createQuickReply(payload: QuickReplyPayload): Promise<QuickReply> {
  const { data } = await apiClient.post<QuickReply>("/api/v1/quick-replies", payload);
  return data;
}

export async function updateQuickReply(
  id: string,
  payload: Partial<QuickReplyPayload>,
): Promise<QuickReply> {
  const { data } = await apiClient.patch<QuickReply>(`/api/v1/quick-replies/${id}`, payload);
  return data;
}

export async function deleteQuickReply(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/quick-replies/${id}`);
}
