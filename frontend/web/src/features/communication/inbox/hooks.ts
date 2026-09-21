import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as inboxApi from "./api";

export const inboxKeys = {
  conversations: ["inbox-conversations"] as const,
  messages: (conversationId: string) => ["inbox-messages", conversationId] as const,
};

export function useConversations() {
  return useQuery({
    queryKey: inboxKeys.conversations,
    queryFn: inboxApi.fetchConversations,
    // Cheap poll so new inbound messages/unread counts show up without the
    // agent needing to manually refresh - same convention as
    // `features/connectors/hooks.ts::useConnectorInstances`.
    refetchInterval: 15_000,
  });
}

export function useMessages(conversationId: string | undefined) {
  return useQuery({
    queryKey: inboxKeys.messages(conversationId ?? ""),
    queryFn: () => inboxApi.fetchMessages(conversationId as string),
    enabled: Boolean(conversationId),
    // Also poll the open thread so a reply that arrives while a
    // conversation is open shows up without reselecting it.
    refetchInterval: 15_000,
  });
}

export function useSendMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ conversationId, content }: { conversationId: string; content: string }) =>
      inboxApi.sendMessage(conversationId, content),
    onSuccess: (_message, variables) => {
      void queryClient.invalidateQueries({ queryKey: inboxKeys.messages(variables.conversationId) });
      void queryClient.invalidateQueries({ queryKey: inboxKeys.conversations });
    },
  });
}

export function useMarkRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => inboxApi.markRead(conversationId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: inboxKeys.conversations });
    },
  });
}

export function useAssignAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ conversationId, agentId }: { conversationId: string; agentId: string | null }) =>
      inboxApi.assignAgent(conversationId, agentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: inboxKeys.conversations });
    },
  });
}
