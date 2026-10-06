import type { AuthTokens, LoginRequest } from "@fusion-flow/ts-types";
import { apiClient } from "./api-client";
import type {
  AdminNodeTypeSummary,
  AuditLogFilters,
  AuditLogPage,
  BillingUsage,
  BusinessTemplate,
  ConnectorAccessOverride,
  ConnectorAccessRequestAdmin,
  ConnectorHealth,
  ConnectorTypeCatalogItem,
  FeatureFlag,
  FeatureFlagCatalogItem,
  FeatureFlagOverride,
  RevokeImpact,
  GraphValidationResult,
  ImpersonateResponse,
  Plan,
  PlanFeatureFlag,
  PlanResourceLimit,
  TemplatesResponse,
  TenantDetail,
  TenantListItem,
  TenantModuleAccess,
  TenantResourceLimit,
  WorkflowComponent,
  WorkflowNodeTemplate,
  WorkflowStarterTemplate,
} from "./admin-types";

export async function login(payload: LoginRequest): Promise<AuthTokens> {
  const { data } = await apiClient.post<AuthTokens>("/api/v1/auth/login", payload);
  return data;
}

export async function logout(): Promise<void> {
  await apiClient.post("/api/v1/auth/logout");
}

// --- Tenants ------------------------------------------------------------------

export async function fetchTenants(): Promise<TenantListItem[]> {
  const { data } = await apiClient.get<TenantListItem[]>("/api/admin/tenants");
  return data;
}

export async function fetchTenantDetail(tenantId: string): Promise<TenantDetail> {
  const { data } = await apiClient.get<TenantDetail>(`/api/admin/tenants/${tenantId}`);
  return data;
}

export async function suspendTenant(tenantId: string): Promise<TenantListItem> {
  const { data } = await apiClient.post<TenantListItem>(`/api/admin/tenants/${tenantId}/suspend`);
  return data;
}

export async function reactivateTenant(tenantId: string): Promise<TenantListItem> {
  const { data } = await apiClient.post<TenantListItem>(`/api/admin/tenants/${tenantId}/reactivate`);
  return data;
}

export async function approveTenant(tenantId: string): Promise<TenantListItem> {
  const { data } = await apiClient.post<TenantListItem>(`/api/admin/tenants/${tenantId}/approve`);
  return data;
}

export async function denyTenant(tenantId: string, reason?: string): Promise<TenantListItem> {
  const { data } = await apiClient.post<TenantListItem>(`/api/admin/tenants/${tenantId}/deny`, {
    reason: reason || null,
  });
  return data;
}

export async function fetchTenantConnectors(tenantId: string): Promise<ConnectorHealth> {
  const { data } = await apiClient.get<ConnectorHealth>(`/api/admin/tenants/${tenantId}/connectors`);
  return data;
}

export async function fetchTenantModuleAccess(tenantId: string): Promise<TenantModuleAccess[]> {
  const { data } = await apiClient.get<TenantModuleAccess[]>(`/api/admin/tenants/${tenantId}/module-access`);
  return data;
}

export async function setConnectorAccessOverride(
  tenantId: string,
  typeKey: string,
  payload: { granted: boolean; reason?: string | null },
): Promise<ConnectorAccessOverride> {
  const { data } = await apiClient.put<ConnectorAccessOverride>(
    `/api/admin/tenants/${tenantId}/connectors/${typeKey}/override`,
    payload,
  );
  return data;
}

export async function fetchRevokeImpact(tenantId: string, typeKey: string): Promise<RevokeImpact> {
  const { data } = await apiClient.get<RevokeImpact>(
    `/api/admin/tenants/${tenantId}/connectors/${typeKey}/revoke-impact`,
  );
  return data;
}

export async function clearConnectorAccessOverride(tenantId: string, typeKey: string): Promise<void> {
  await apiClient.delete(`/api/admin/tenants/${tenantId}/connectors/${typeKey}/override`);
}

export async function impersonateTenantUser(
  tenantId: string,
  payload: { target_user_id: string; reason: string },
): Promise<ImpersonateResponse> {
  const { data } = await apiClient.post<ImpersonateResponse>(
    `/api/admin/tenants/${tenantId}/impersonate`,
    payload,
  );
  return data;
}

// --- Audit log ------------------------------------------------------------------

export async function fetchAuditLog(filters: AuditLogFilters): Promise<AuditLogPage> {
  const { data } = await apiClient.get<AuditLogPage>("/api/admin/audit-log", { params: filters });
  return data;
}

// --- Feature flags ---------------------------------------------------------------

export async function fetchFeatureFlags(): Promise<FeatureFlag[]> {
  const { data } = await apiClient.get<FeatureFlag[]>("/api/admin/feature-flags");
  return data;
}

export async function fetchFeatureFlagCatalog(): Promise<FeatureFlagCatalogItem[]> {
  const { data } = await apiClient.get<FeatureFlagCatalogItem[]>("/api/admin/feature-flags/catalog");
  return data;
}

export async function createFeatureFlag(payload: {
  key: string;
  description?: string | null;
  is_global_default: boolean;
}): Promise<FeatureFlag> {
  const { data } = await apiClient.post<FeatureFlag>("/api/admin/feature-flags", payload);
  return data;
}

export async function updateFeatureFlag(
  flagId: string,
  payload: { description?: string | null; is_global_default?: boolean },
): Promise<FeatureFlag> {
  const { data } = await apiClient.patch<FeatureFlag>(`/api/admin/feature-flags/${flagId}`, payload);
  return data;
}

export async function fetchFeatureFlagOverrides(flagId: string): Promise<FeatureFlagOverride[]> {
  const { data } = await apiClient.get<FeatureFlagOverride[]>(
    `/api/admin/feature-flags/${flagId}/overrides`,
  );
  return data;
}

export async function upsertFeatureFlagOverride(
  flagId: string,
  payload: { tenant_id: string | null; enabled: boolean },
): Promise<FeatureFlagOverride> {
  const { data } = await apiClient.post<FeatureFlagOverride>(
    `/api/admin/feature-flags/${flagId}/overrides`,
    payload,
  );
  return data;
}

// --- Global field templates ----------------------------------------------------

export async function fetchTemplates(): Promise<TemplatesResponse> {
  const { data } = await apiClient.get<TemplatesResponse>("/api/admin/templates");
  return data;
}

// --- Plans -------------------------------------------------------------------

export async function fetchPlans(): Promise<Plan[]> {
  const { data } = await apiClient.get<Plan[]>("/api/admin/plans");
  return data;
}

export async function createPlan(payload: { key: string; name: string; is_default: boolean }): Promise<Plan> {
  const { data } = await apiClient.post<Plan>("/api/admin/plans", payload);
  return data;
}

export async function updatePlan(
  planId: string,
  payload: { name?: string; is_default?: boolean },
): Promise<Plan> {
  const { data } = await apiClient.patch<Plan>(`/api/admin/plans/${planId}`, payload);
  return data;
}

export async function fetchPlanFeatureFlags(planId: string): Promise<PlanFeatureFlag[]> {
  const { data } = await apiClient.get<PlanFeatureFlag[]>(`/api/admin/plans/${planId}/feature-flags`);
  return data;
}

export async function setPlanFeatureFlags(
  planId: string,
  flags: { feature_flag_id: string; enabled: boolean }[],
): Promise<PlanFeatureFlag[]> {
  const { data } = await apiClient.put<PlanFeatureFlag[]>(`/api/admin/plans/${planId}/feature-flags`, {
    flags,
  });
  return data;
}

export async function fetchPlanResourceLimits(planId: string): Promise<PlanResourceLimit[]> {
  const { data } = await apiClient.get<PlanResourceLimit[]>(`/api/admin/plans/${planId}/resource-limits`);
  return data;
}

export async function setPlanResourceLimits(
  planId: string,
  limits: { resource_key: string; max_count: number | null }[],
): Promise<PlanResourceLimit[]> {
  const { data } = await apiClient.put<PlanResourceLimit[]>(`/api/admin/plans/${planId}/resource-limits`, {
    limits,
  });
  return data;
}

export async function fetchTenantResourceLimits(tenantId: string): Promise<TenantResourceLimit[]> {
  const { data } = await apiClient.get<TenantResourceLimit[]>(`/api/admin/tenants/${tenantId}/resource-limits`);
  return data;
}

export async function setTenantResourceLimit(
  tenantId: string,
  resourceKey: string,
  maxCount: number,
): Promise<TenantResourceLimit> {
  const { data } = await apiClient.put<TenantResourceLimit>(
    `/api/admin/tenants/${tenantId}/resource-limits/${resourceKey}`,
    { max_count: maxCount },
  );
  return data;
}

export async function clearTenantResourceLimit(tenantId: string, resourceKey: string): Promise<void> {
  await apiClient.delete(`/api/admin/tenants/${tenantId}/resource-limits/${resourceKey}`);
}

export async function assignTenantPlan(tenantId: string, planId: string | null): Promise<TenantListItem> {
  const { data } = await apiClient.post<TenantListItem>(`/api/admin/tenants/${tenantId}/plan`, {
    plan_id: planId,
  });
  return data;
}

// --- Business templates (starter kits) ----------------------------------------

export async function fetchBusinessTemplates(): Promise<BusinessTemplate[]> {
  const { data } = await apiClient.get<BusinessTemplate[]>("/api/admin/business-templates");
  return data;
}

export async function fetchBusinessTemplate(templateId: string): Promise<BusinessTemplate> {
  const { data } = await apiClient.get<BusinessTemplate>(`/api/admin/business-templates/${templateId}`);
  return data;
}

export interface BusinessTemplateInput {
  key: string;
  name: string;
  description?: string | null;
  vertical?: string | null;
  plan_id?: string | null;
  is_active: boolean;
  connector_type_ids: string[];
}

export async function createBusinessTemplate(payload: BusinessTemplateInput): Promise<BusinessTemplate> {
  const { data } = await apiClient.post<BusinessTemplate>("/api/admin/business-templates", payload);
  return data;
}

export async function updateBusinessTemplate(
  templateId: string,
  payload: Partial<BusinessTemplateInput>,
): Promise<BusinessTemplate> {
  const { data } = await apiClient.patch<BusinessTemplate>(
    `/api/admin/business-templates/${templateId}`,
    payload,
  );
  return data;
}

// --- Workflow node templates (admin-managed palette entries, Part D) -----

export async function fetchWorkflowNodeTemplates(): Promise<WorkflowNodeTemplate[]> {
  const { data } = await apiClient.get<WorkflowNodeTemplate[]>("/api/admin/workflow-node-templates");
  return data;
}

export interface WorkflowNodeTemplateInput {
  key: string;
  label: string;
  description?: string | null;
  category: string;
  base_node_type: string;
  icon?: string | null;
  default_config: Record<string, unknown>;
  config_schema_overrides?: Record<string, unknown> | null;
  is_active: boolean;
}

export async function createWorkflowNodeTemplate(
  payload: WorkflowNodeTemplateInput,
): Promise<WorkflowNodeTemplate> {
  const { data } = await apiClient.post<WorkflowNodeTemplate>(
    "/api/admin/workflow-node-templates",
    payload,
  );
  return data;
}

export async function updateWorkflowNodeTemplate(
  templateId: string,
  payload: Partial<Omit<WorkflowNodeTemplateInput, "base_node_type">>,
): Promise<WorkflowNodeTemplate> {
  const { data } = await apiClient.patch<WorkflowNodeTemplate>(
    `/api/admin/workflow-node-templates/${templateId}`,
    payload,
  );
  return data;
}

export async function deleteWorkflowNodeTemplate(templateId: string): Promise<void> {
  await apiClient.delete(`/api/admin/workflow-node-templates/${templateId}`);
}

// --- Registered node types (admin-facing summary, drives the workflow
// node template's base_node_type dropdown - never goes stale relative to
// what's actually registered, unlike a hand-maintained list) -------------

export async function fetchAdminNodeTypes(): Promise<AdminNodeTypeSummary[]> {
  const { data } = await apiClient.get<AdminNodeTypeSummary[]>("/api/admin/node-types");
  return data;
}

// --- Workflow starter templates (whole-new-workflow seeds) ---------------

export async function fetchWorkflowStarterTemplates(): Promise<WorkflowStarterTemplate[]> {
  const { data } = await apiClient.get<WorkflowStarterTemplate[]>("/api/admin/workflow-starter-templates");
  return data;
}

export interface WorkflowStarterTemplateInput {
  key: string;
  name: string;
  description?: string | null;
  category: string;
  icon?: string | null;
  graph_json: Record<string, unknown>;
  required_object_types?: Record<string, unknown>[] | null;
  setup_notes?: string | null;
  is_active: boolean;
}

export async function createWorkflowStarterTemplate(
  payload: WorkflowStarterTemplateInput,
): Promise<WorkflowStarterTemplate> {
  const { data } = await apiClient.post<WorkflowStarterTemplate>(
    "/api/admin/workflow-starter-templates",
    payload,
  );
  return data;
}

export async function updateWorkflowStarterTemplate(
  templateId: string,
  payload: Partial<Omit<WorkflowStarterTemplateInput, "key">>,
): Promise<WorkflowStarterTemplate> {
  const { data } = await apiClient.patch<WorkflowStarterTemplate>(
    `/api/admin/workflow-starter-templates/${templateId}`,
    payload,
  );
  return data;
}

export async function deleteWorkflowStarterTemplate(templateId: string): Promise<void> {
  await apiClient.delete(`/api/admin/workflow-starter-templates/${templateId}`);
}

export async function validateWorkflowStarterTemplateGraph(
  graphJson: Record<string, unknown>,
): Promise<GraphValidationResult> {
  const { data } = await apiClient.post<GraphValidationResult>(
    "/api/admin/workflow-starter-templates/validate",
    { graph_json: graphJson },
  );
  return data;
}

// --- Workflow components (insertable node/edge fragments) ----------------

export async function fetchWorkflowComponents(): Promise<WorkflowComponent[]> {
  const { data } = await apiClient.get<WorkflowComponent[]>("/api/admin/workflow-components");
  return data;
}

export interface WorkflowComponentInput {
  key: string;
  name: string;
  description?: string | null;
  category: string;
  icon?: string | null;
  graph_fragment: Record<string, unknown>;
  required_object_types?: Record<string, unknown>[] | null;
  setup_notes?: string | null;
  is_active: boolean;
}

export async function createWorkflowComponent(payload: WorkflowComponentInput): Promise<WorkflowComponent> {
  const { data } = await apiClient.post<WorkflowComponent>("/api/admin/workflow-components", payload);
  return data;
}

export async function updateWorkflowComponent(
  componentId: string,
  payload: Partial<Omit<WorkflowComponentInput, "key">>,
): Promise<WorkflowComponent> {
  const { data } = await apiClient.patch<WorkflowComponent>(
    `/api/admin/workflow-components/${componentId}`,
    payload,
  );
  return data;
}

export async function deleteWorkflowComponent(componentId: string): Promise<void> {
  await apiClient.delete(`/api/admin/workflow-components/${componentId}`);
}

export async function validateWorkflowComponentGraph(
  graphFragment: Record<string, unknown>,
): Promise<GraphValidationResult> {
  const { data } = await apiClient.post<GraphValidationResult>(
    "/api/admin/workflow-components/validate",
    { graph_fragment: graphFragment },
  );
  return data;
}

export async function fetchConnectorTypeCatalog(): Promise<ConnectorTypeCatalogItem[]> {
  const { data } = await apiClient.get<ConnectorTypeCatalogItem[]>("/api/admin/connector-types");
  return data;
}

// --- Connector access requests -------------------------------------------------

export async function fetchConnectorAccessRequests(status?: string): Promise<ConnectorAccessRequestAdmin[]> {
  const { data } = await apiClient.get<ConnectorAccessRequestAdmin[]>(
    "/api/admin/connector-access-requests",
    { params: status ? { status } : undefined },
  );
  return data;
}

export async function approveConnectorAccessRequest(requestId: string): Promise<void> {
  await apiClient.post(`/api/admin/connector-access-requests/${requestId}/approve`);
}

export async function denyConnectorAccessRequest(requestId: string): Promise<void> {
  await apiClient.post(`/api/admin/connector-access-requests/${requestId}/deny`);
}

// --- Billing (stub) ----------------------------------------------------------------

export async function fetchBillingUsage(): Promise<BillingUsage> {
  const { data } = await apiClient.get<BillingUsage>("/api/admin/billing-usage");
  return data;
}
