import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as whatsappAutomationsApi from "./api";
import type { CreateWhatsAppAutomationPayload, WhatsAppAppointmentBookingConfig } from "./api";

export const whatsappAutomationKeys = {
  all: ["whatsapp-automations"] as const,
};

export function useWhatsAppAutomations() {
  return useQuery({
    queryKey: whatsappAutomationKeys.all,
    queryFn: whatsappAutomationsApi.fetchWhatsAppAutomations,
  });
}

export function useCreateWhatsAppAutomation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateWhatsAppAutomationPayload) =>
      whatsappAutomationsApi.createWhatsAppAutomation(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: whatsappAutomationKeys.all });
    },
  });
}

export function useUpdateWhatsAppAutomation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, config }: { id: string; config: WhatsAppAppointmentBookingConfig }) =>
      whatsappAutomationsApi.updateWhatsAppAutomation(id, config),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: whatsappAutomationKeys.all });
    },
  });
}

export function useSetWhatsAppAutomationActive() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      whatsappAutomationsApi.setWhatsAppAutomationActive(id, isActive),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: whatsappAutomationKeys.all });
    },
  });
}

export function useDeleteWhatsAppAutomation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => whatsappAutomationsApi.deleteWhatsAppAutomation(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: whatsappAutomationKeys.all });
    },
  });
}
