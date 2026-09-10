import { apiClient } from "../../lib/api-client";
import type {
  ConnectorAccessRequest,
  ConnectorType,
  ConnectorInstance,
  ConnectorEvent,
  ConnectRequest,
  ConnectResponse,
} from "./types";

/**
 * Talks to the generic connector lifecycle routes
 * (`backend/src/fusionflow/modules/connectors/router.py`). Every function
 * here maps 1:1 to one backend endpoint - no client-side branching on
 * provider, matching the framework's genericity guarantee on the backend.
 */

export async function fetchConnectorTypes(): Promise<ConnectorType[]> {
  const { data } = await apiClient.get<ConnectorType[]>("/api/v1/connectors/types");
  return data;
}

export async function fetchConnectorInstances(): Promise<ConnectorInstance[]> {
  const { data } = await apiClient.get<ConnectorInstance[]>("/api/v1/connectors");
  return data;
}

export async function connectConnector(typeKey: string, payload: ConnectRequest): Promise<ConnectResponse> {
  const { data } = await apiClient.post<ConnectResponse>(`/api/v1/connectors/${typeKey}/connect`, payload);
  return data;
}

export async function testConnector(instanceId: string): Promise<ConnectorInstance> {
  const { data } = await apiClient.post<ConnectorInstance>(`/api/v1/connectors/${instanceId}/test`);
  return data;
}

export async function disconnectConnector(instanceId: string): Promise<ConnectorInstance> {
  const { data } = await apiClient.post<ConnectorInstance>(`/api/v1/connectors/${instanceId}/disconnect`);
  return data;
}

export async function fetchConnectorEvents(instanceId: string): Promise<ConnectorEvent[]> {
  const { data } = await apiClient.get<ConnectorEvent[]>(`/api/v1/connectors/${instanceId}/events`);
  return data;
}

/**
 * `POST /api/v1/connectors/{typeKey}/request-access` — asks an admin to
 * grant a connector outside the tenant's business-template bundle.
 */
export async function requestConnectorAccess(
  typeKey: string,
  reason?: string,
): Promise<ConnectorAccessRequest> {
  const { data } = await apiClient.post<ConnectorAccessRequest>(
    `/api/v1/connectors/${typeKey}/request-access`,
    { reason },
  );
  return data;
}
