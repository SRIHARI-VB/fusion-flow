import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as quickRepliesApi from "./api";
import type { QuickReplyPayload } from "./types";

export const quickReplyKeys = {
  list: ["quick-replies"] as const,
};

export function useQuickReplies() {
  return useQuery({ queryKey: quickReplyKeys.list, queryFn: quickRepliesApi.fetchQuickReplies });
}

export function useCreateQuickReply() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: QuickReplyPayload) => quickRepliesApi.createQuickReply(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: quickReplyKeys.list });
    },
  });
}

export function useUpdateQuickReply() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Partial<QuickReplyPayload> }) =>
      quickRepliesApi.updateQuickReply(id, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: quickReplyKeys.list });
    },
  });
}

export function useDeleteQuickReply() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => quickRepliesApi.deleteQuickReply(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: quickReplyKeys.list });
    },
  });
}
