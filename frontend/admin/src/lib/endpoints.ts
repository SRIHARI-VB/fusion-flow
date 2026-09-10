import type { AuthTokens, LoginRequest } from "@fusion-flow/ts-types";
import { apiClient } from "./api-client";
import type {
  AuditLogFilters,
  AuditLogPage,
  BillingUsage,
  ConnectorHealth,
  FeatureFlag,
  FeatureFlagOverride,
  ImpersonateResponse,
  TemplatesResponse,
  TenantDetail,
  TenantListItem,
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

export async function fetchTenantConnectors(tenantId: string): Promise<ConnectorHealth> {
  const { data } = await apiClient.get<ConnectorHealth>(`/api/admin/tenants/${tenantId}/connectors`);
  return data;
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

// --- Billing (stub) ----------------------------------------------------------------

export async function fetchBillingUsage(): Promise<BillingUsage> {
  const { data } = await apiClient.get<BillingUsage>("/api/admin/billing-usage");
  return data;
}
