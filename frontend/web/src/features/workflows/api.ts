import { apiClient } from "../../lib/api-client";
import type {
  NodeType,
  PublishResponse,
  Workflow,
  WorkflowGraphJson,
  WorkflowRun,
  WorkflowRunDetail,
  WorkflowVersion,
} from "./types";

const BASE = "/api/v1/workflows";

export async function listWorkflows(): Promise<Workflow[]> {
  const { data } = await apiClient.get<Workflow[]>(BASE);
  return data;
}

export async function getWorkflow(id: string): Promise<Workflow> {
  const { data } = await apiClient.get<Workflow>(`${BASE}/${id}`);
  return data;
}

export async function createWorkflow(payload: {
  name: string;
  graph?: WorkflowGraphJson;
}): Promise<Workflow> {
  const { data } = await apiClient.post<Workflow>(BASE, payload);
  return data;
}

export async function updateWorkflow(
  id: string,
  payload: { name?: string; graph?: WorkflowGraphJson },
): Promise<WorkflowVersion> {
  const { data } = await apiClient.patch<WorkflowVersion>(`${BASE}/${id}`, payload);
  return data;
}

export async function publishWorkflow(id: string): Promise<PublishResponse> {
  const { data } = await apiClient.post<PublishResponse>(`${BASE}/${id}/publish`);
  return data;
}

export async function listWorkflowVersions(id: string): Promise<WorkflowVersion[]> {
  const { data } = await apiClient.get<WorkflowVersion[]>(`${BASE}/${id}/versions`);
  return data;
}

export async function simulateWorkflow(
  id: string,
  payload: Record<string, unknown>,
): Promise<WorkflowRunDetail> {
  const { data } = await apiClient.post<WorkflowRunDetail>(`${BASE}/${id}/simulate`, { payload });
  return data;
}

export async function listWorkflowRuns(id: string): Promise<WorkflowRun[]> {
  const { data } = await apiClient.get<WorkflowRun[]>(`${BASE}/${id}/runs`);
  return data;
}

export async function getWorkflowRun(runId: string): Promise<WorkflowRunDetail> {
  const { data } = await apiClient.get<WorkflowRunDetail>(`${BASE}/runs/${runId}`);
  return data;
}

export async function listNodeTypes(): Promise<NodeType[]> {
  const { data } = await apiClient.get<NodeType[]>(`${BASE}/node-types`);
  return data;
}
