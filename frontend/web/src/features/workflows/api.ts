import { apiClient } from "../../lib/api-client";
import type {
  ModuleCatalogEntry,
  NodeType,
  PublishResponse,
  Workflow,
  WorkflowComponent,
  WorkflowGraphJson,
  WorkflowPurpose,
  WorkflowRun,
  WorkflowRunDetail,
  WorkflowStarterTemplate,
  WorkflowVersion,
} from "./types";
import type { RecipientSource } from "./components/RecipientSourceField";

/** `WorkflowSchedule` CRUD (recurring/scheduled bulk-send support for
 * "Broadcast"-purpose workflows) - mirrors the backend contract landing in
 * parallel (see `SchedulePanel.tsx`). Field names may shift slightly once
 * that work lands; this is the shape to build against for now. */
export type ScheduleFrequency = "once" | "daily" | "weekly" | "monthly";

export interface WorkflowSchedule {
  id: string;
  workflow_id: string;
  frequency: ScheduleFrequency;
  run_at?: string;
  time_of_day?: string;
  weekdays?: number[];
  day_of_month?: number;
  timezone: string;
  recipient_source: RecipientSource;
  next_run_at: string;
  is_active: boolean;
  last_run_at?: string;
  last_run_status?: string;
}

export type WorkflowSchedulePayload = Omit<WorkflowSchedule, "id" | "workflow_id" | "next_run_at" | "last_run_at" | "last_run_status">;

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
  /** Defaults to `"automation"` server-side when omitted - see
   * `WorkflowsListPage.tsx`'s new "purpose" step. */
  purpose?: WorkflowPurpose;
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

/** `purpose` narrows which triggers come back (an "automation" workflow
 * only offers reactive WhatsApp/order/payment triggers; a "broadcast"
 * workflow only offers `broadcast.scheduled_send`) - optional and omitted
 * today by `WorkflowEditorPage.tsx`'s call site (that wiring is a
 * follow-up: it'll need `queryFn: () => listNodeTypes(purpose)`, same
 * wrapped-arrow pattern `useResourceLimits.ts` already uses for
 * `fetchResourceUsage`, since today's call site passes this function
 * bare as `queryFn: listNodeTypes` and so can't pass the option through
 * anyway).
 *
 * Declared via an overload (rather than one `purpose?: WorkflowPurpose`
 * signature) so that bare `queryFn: listNodeTypes` reference keeps
 * type-checking against react-query's `QueryFunction<NodeType[], ...>`
 * (which calls with a `QueryFunctionContext`, not a `WorkflowPurpose`) -
 * a single optional-param signature, or an all-optional-properties
 * options object, both fail that bare-reference assignability check. */
export function listNodeTypes(): Promise<NodeType[]>;
export function listNodeTypes(purpose: WorkflowPurpose): Promise<NodeType[]>;
export async function listNodeTypes(purpose?: WorkflowPurpose): Promise<NodeType[]> {
  const { data } = await apiClient.get<NodeType[]>(`${BASE}/node-types`, {
    params: purpose ? { purpose } : undefined,
  });
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

/** Recurring/scheduled bulk-send config for a "Broadcast"-purpose
 * workflow's `broadcast.scheduled_send` trigger - see `SchedulePanel.tsx`. */
export async function listSchedules(workflowId: string): Promise<WorkflowSchedule[]> {
  const { data } = await apiClient.get<WorkflowSchedule[]>(`${BASE}/${workflowId}/schedules`);
  return data;
}

export async function createSchedule(
  workflowId: string,
  payload: WorkflowSchedulePayload,
): Promise<WorkflowSchedule> {
  const { data } = await apiClient.post<WorkflowSchedule>(`${BASE}/${workflowId}/schedules`, payload);
  return data;
}

export async function updateSchedule(
  workflowId: string,
  scheduleId: string,
  payload: Partial<WorkflowSchedulePayload>,
): Promise<WorkflowSchedule> {
  const { data } = await apiClient.patch<WorkflowSchedule>(
    `${BASE}/${workflowId}/schedules/${scheduleId}`,
    payload,
  );
  return data;
}

export async function deleteSchedule(workflowId: string, scheduleId: string): Promise<void> {
  await apiClient.delete(`${BASE}/${workflowId}/schedules/${scheduleId}`);
}

/**
 * Uploads a file to a tenant's connected `cloudflare_r2` storage instance
 * and returns its public URL - backs `MediaUploadButton.tsx`'s "Upload a
 * file" option for `whatsapp.send_message`'s Media/Template content types.
 * Lives here (rather than `features/connectors/api.ts`) since it's only
 * ever called from a workflow node's config editor; the request itself
 * still targets the generic connector-instance-scoped route convention
 * `features/connectors/api.ts` already uses for `testConnector`/
 * `fetchConnectorEvents` (`/api/v1/connectors/{instanceId}/...`), not the
 * `${BASE}` (`/api/v1/workflows`) prefix used everywhere else in this file.
 * `apiClient` infers the `multipart/form-data` Content-Type (with
 * boundary) from the `FormData` body on its own - don't set it manually.
 */
export async function uploadMedia(instanceId: string, file: File): Promise<{ url: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await apiClient.post<{ url: string }>(
    `/api/v1/connectors/${instanceId}/media`,
    formData,
  );
  return data;
}
