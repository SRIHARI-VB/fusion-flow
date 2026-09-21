import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as instagramApi from "./api";
import type { CreateInstagramAutomationPayload, InstagramCommentAutomationConfig } from "./types";

export const instagramAutomationKeys = {
  all: ["instagram-automations"] as const,
};

export function useInstagramAutomations() {
  return useQuery({
    queryKey: instagramAutomationKeys.all,
    queryFn: instagramApi.fetchInstagramAutomations,
  });
}

export function useCreateInstagramAutomation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateInstagramAutomationPayload) => instagramApi.createInstagramAutomation(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: instagramAutomationKeys.all });
    },
  });
}

export function useUpdateInstagramAutomation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, config }: { id: string; config: InstagramCommentAutomationConfig }) =>
      instagramApi.updateInstagramAutomation(id, config),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: instagramAutomationKeys.all });
    },
  });
}

export function useSetInstagramAutomationActive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      instagramApi.setInstagramAutomationActive(id, isActive),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: instagramAutomationKeys.all });
    },
  });
}

export function useDeleteInstagramAutomation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => instagramApi.deleteInstagramAutomation(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: instagramAutomationKeys.all });
    },
  });
}
