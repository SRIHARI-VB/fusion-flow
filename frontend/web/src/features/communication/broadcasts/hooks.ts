import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as campaignsApi from "./api";
import type { CreateBroadcastCampaignPayload } from "./types";

export const broadcastCampaignKeys = {
  list: ["broadcast-campaigns"] as const,
  detail: (id: string) => ["broadcast-campaigns", id] as const,
};

export function useCampaigns() {
  return useQuery({ queryKey: broadcastCampaignKeys.list, queryFn: campaignsApi.fetchCampaigns });
}

export function useCampaign(id: string | undefined) {
  return useQuery({
    queryKey: broadcastCampaignKeys.detail(id ?? ""),
    queryFn: () => campaignsApi.getCampaign(id as string),
    enabled: Boolean(id),
  });
}

export function useCreateCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateBroadcastCampaignPayload) => campaignsApi.createCampaign(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: broadcastCampaignKeys.list });
    },
  });
}

export function useSetCampaignActive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      campaignsApi.setCampaignActive(id, isActive),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: broadcastCampaignKeys.list });
    },
  });
}

export function useDeleteCampaign() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => campaignsApi.deleteCampaign(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: broadcastCampaignKeys.list });
    },
  });
}
