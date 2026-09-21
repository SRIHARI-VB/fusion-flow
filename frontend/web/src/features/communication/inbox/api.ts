import { apiClient } from "../../../lib/api-client";
import type { Conversation, Message } from "./types";

/**
 * Talks to the Unified Inbox routes
 * (`backend/src/fusionflow/modules/inbox/router.py`), mounted under
 * `/api/v1/inbox/...`. Every function here maps 1:1 to one backend
 * endpoint, same convention as `features/connectors/api.ts`.
 */

export async function fetchConversations(): Promise<Conversation[]> {
  const { data } = await apiClient.get<Conversation[]>("/api/v1/inbox/conversations");
  return data;
}

export async function fetchMessages(conversationId: string): Promise<Message[]> {
  const { data } = await apiClient.get<Message[]>(
    `/api/v1/inbox/conversations/${conversationId}/messages`,
  );
  return data;
}

export async function sendMessage(conversationId: string, content: string): Promise<Message> {
  const { data } = await apiClient.post<Message>(
    `/api/v1/inbox/conversations/${conversationId}/messages`,
    { content },
  );
  return data;
}

export async function markRead(conversationId: string): Promise<Conversation> {
  const { data } = await apiClient.post<Conversation>(
    `/api/v1/inbox/conversations/${conversationId}/read`,
  );
  return data;
}

export async function assignAgent(
  conversationId: string,
  agentId: string | null,
): Promise<Conversation> {
  const { data } = await apiClient.post<Conversation>(
    `/api/v1/inbox/conversations/${conversationId}/assign`,
    { agent_id: agentId },
  );
  return data;
}
