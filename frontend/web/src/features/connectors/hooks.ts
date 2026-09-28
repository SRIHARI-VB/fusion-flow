import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as connectorsApi from "./api";
import type { ConnectRequest, SetRoleRestrictionRequest } from "./types";

export const connectorKeys = {
  types: ["connector-types"] as const,
  instances: ["connector-instances"] as const,
  events: (instanceId: string) => ["connector-events", instanceId] as const,
  roleAccess: ["module-role-access"] as const,
};

export function useConnectorTypes() {
  return useQuery({ queryKey: connectorKeys.types, queryFn: connectorsApi.fetchConnectorTypes });
}

export function useConnectorInstances() {
  return useQuery({
    queryKey: connectorKeys.instances,
    queryFn: connectorsApi.fetchConnectorInstances,
    // Cheap poll so state/health flips (e.g. after a webhook lands) show up
    // without the tenant needing to manually refresh the page.
    refetchInterval: 15_000,
  });
}

export function useConnectorEvents(instanceId: string | undefined) {
  return useQuery({
    queryKey: connectorKeys.events(instanceId ?? ""),
    queryFn: () => connectorsApi.fetchConnectorEvents(instanceId as string),
    enabled: Boolean(instanceId),
  });
}

export function useConnectConnector() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ typeKey, payload }: { typeKey: string; payload: ConnectRequest }) =>
      connectorsApi.connectConnector(typeKey, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: connectorKeys.instances });
    },
  });
}

export function useTestConnector() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (instanceId: string) => connectorsApi.testConnector(instanceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: connectorKeys.instances });
    },
  });
}

export function useDisconnectConnector() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (instanceId: string) => connectorsApi.disconnectConnector(instanceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: connectorKeys.instances });
    },
  });
}

export function useRequestConnectorAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ typeKey, reason }: { typeKey: string; reason?: string }) =>
      connectorsApi.requestConnectorAccess(typeKey, reason),
    onSuccess: () => {
      // Re-fetch /connectors/types so the card flips to "Pending admin approval".
      void queryClient.invalidateQueries({ queryKey: connectorKeys.types });
    },
  });
}

export function useModuleRoleAccess() {
  return useQuery({ queryKey: connectorKeys.roleAccess, queryFn: connectorsApi.fetchModuleRoleAccess });
}

export function useSetRoleRestriction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SetRoleRestrictionRequest) => connectorsApi.setRoleRestriction(payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: connectorKeys.roleAccess });
      // A restricted-for-Member/Viewer module affects nav/RequireModule for
      // whoever is logged in as that role right now.
      void queryClient.invalidateQueries({ queryKey: connectorKeys.types });
    },
  });
}
