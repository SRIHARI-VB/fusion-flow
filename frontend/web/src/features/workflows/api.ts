import { apiClient } from "../../lib/api-client";
import type {
  ModuleCatalogEntry,
  NodeType,
  PublishResponse,
  Workflow,
  WorkflowComponent,
  WorkflowGraphJson,
  WorkflowRun,
  WorkflowRunDetail,
  WorkflowStarterTemplate,
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
  /** When set, `graph` above is ignored server-side and the new
   * workflow's graph is seeded from this `WorkflowStarterTemplate` id
   * instead (see `StarterTemplatePicker.tsx`). */
  starter_template_id?: string;
}): Promise<Workflow> {
  const { data } = await apiClient.post<Workflow>(BASE, payload);
  return data;
}

export async function deleteWorkflow(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/${id}`);
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

/** The unified module picker (fixed modules + this tenant's own custom
 * object types) - feeds `records.query`/`records.upsert`'s module select
 * and `whatsapp.ask_choice`'s module-sourced option list. */
export async function listModules(): Promise<ModuleCatalogEntry[]> {
  const { data } = await apiClient.get<ModuleCatalogEntry[]>(`${BASE}/modules`);
  return data;
}

/** Ready-to-use example workflows a tenant can start a new workflow from
 * (composable-builder redesign, Phase 6) - see `StarterTemplatePicker.tsx`. */
export async function listStarterTemplates(): Promise<WorkflowStarterTemplate[]> {
  const { data } = await apiClient.get<WorkflowStarterTemplate[]>(`${BASE}/starter-templates`);
  return data;
}

/** Every insertable fragment this tenant can use: the admin-curated
 * catalog plus this tenant's own saved selections - see
 * `ComponentPicker.tsx`. */
export async function listComponents(): Promise<WorkflowComponent[]> {
  const { data } = await apiClient.get<WorkflowComponent[]>(`${BASE}/components`);
  return data;
}

export async function createComponent(payload: {
  name: string;
  description?: string | null;
  category?: string | null;
  icon?: string | null;
  graph_fragment: WorkflowGraphJson;
}): Promise<WorkflowComponent> {
  const { data } = await apiClient.post<WorkflowComponent>(`${BASE}/components`, payload);
  return data;
}

export async function deleteComponent(id: string): Promise<void> {
  await apiClient.delete(`${BASE}/components/${id}`);
}

/** Auto-provisions any custom object type the component's fragment
 * assumes exists - call this before merging the fragment into the
 * canvas (see `WorkflowEditorPage.tsx`'s "insert a component" action). */
export async function provisionComponent(id: string): Promise<void> {
  await apiClient.post(`${BASE}/components/${id}/provision`);
}
