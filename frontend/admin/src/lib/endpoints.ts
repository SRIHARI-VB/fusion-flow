import type { AuthTokens, LoginRequest } from "@fusion-flow/ts-types";
import { apiClient } from "./api-client";
import type {
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
  ImpersonateResponse,
  Plan,
  PlanFeatureFlag,
  TemplatesResponse,
  TenantDetail,
  TenantListItem,
  TenantModuleAccess,
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
