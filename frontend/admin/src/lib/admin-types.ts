/**
 * Hand-written types mirroring `backend/src/fusionflow/modules/admin/schemas.py`.
 * Kept local to `frontend/admin` (not the shared `@fusion-flow/ts-types` package)
 * since these are admin-only DTOs with no tenant-facing consumer - see
 * `frontend/packages/ts-types/README.md`: that package becomes
 * OpenAPI-generated once more endpoints exist, at which point this file goes away.
 */
import type { BusinessStatus, MembershipRole } from "@fusion-flow/ts-types";

export interface TenantListItem {
  id: string;
  name: string;
  slug: string;
  vertical: string | null;
  status: BusinessStatus;
  member_count: number;
  created_at: string;
  denial_reason?: string | null;
}

export interface TenantMembership {
  user_id: string;
  email: string;
  role: MembershipRole;
  invited_at: string;
  accepted_at: string | null;
}

export interface TenantDetail {
  id: string;
  name: string;
  slug: string;
  vertical: string | null;
  status: BusinessStatus;
  onboarding_completed_at: string | null;
  created_at: string;
  memberships: TenantMembership[];
  denial_reason?: string | null;
}

export interface ConnectorHealthItem {
  id: string;
  connector_type_key: string;
  state: string;
  last_webhook_at: string | null;
  last_sync_at: string | null;
}

export interface ConnectorHealth {
  available: boolean;
  reason?: string | null;
  connectors: ConnectorHealthItem[];
}

export interface ImpersonateResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  impersonated: boolean;
  acting_admin_id: string;
  target_user_id: string;
  target_business_id: string;
  impersonation_session_id: string;
}

export interface AuditLogEntry {
  id: string;
  actor_user_id: string | null;
  actor_is_platform_admin: boolean;
  tenant_id: string | null;
  action: string;
  target_type: string | null;
  target_id: string | null;
  extra_metadata: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string;
}

export interface AuditLogPage {
  items: AuditLogEntry[];
  total: number;
}

export interface AuditLogFilters {
  actor_user_id?: string;
  tenant_id?: string;
  action?: string;
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

export interface FeatureFlag {
  id: string;
  key: string;
  description: string | null;
  is_global_default: boolean;
  created_at: string;
}

/** One entry of the "known flags" catalog - what the New Flag dropdown offers. */
export interface FeatureFlagCatalogItem {
  key: string;
  label: string;
  description: string;
  gates_real_behavior: boolean;
}

export interface FeatureFlagOverride {
  id: string;
  feature_flag_id: string;
  tenant_id: string | null;
  enabled: boolean;
}

export interface FieldTemplate {
  id: string;
  vertical: string;
  entity_type: string;
  name: string;
  version: number;
  is_global: boolean;
  field_count: number;
}

export interface FieldTemplatesUnavailable {
  available: false;
  reason: string;
}

export type TemplatesResponse = FieldTemplate[] | FieldTemplatesUnavailable;

export function templatesAvailable(response: TemplatesResponse): response is FieldTemplate[] {
  return Array.isArray(response);
}

export interface BillingUsage {
  available: boolean;
  reason: string;
  tenants_count: number;
}

// --- Plans / business templates / connector access requests ------------------
//
// Mirrors backend/src/fusionflow/modules/admin/schemas.py's Plan*/BusinessTemplate*/
// ConnectorAccessRequest* DTOs, added for the "business templates, connector access
// requests, and plan entitlements" feature.

export interface Plan {
  id: string;
  key: string;
  name: string;
  is_default: boolean;
  created_at: string;
}

export interface PlanFeatureFlag {
  id: string;
  plan_id: string;
  feature_flag_id: string;
  enabled: boolean;
}

export interface BusinessTemplate {
  id: string;
  key: string;
  name: string;
  description: string | null;
  vertical: string | null;
  plan_id: string | null;
  is_active: boolean;
  created_at: string;
  connector_type_ids: string[];
}

export interface ConnectorTypeCatalogItem {
  id: string;
  key: string;
  display_name: string;
  category: string;
}

export type ConnectorAccessRequestStatus = "pending" | "approved" | "denied";

export interface ConnectorAccessRequestAdmin {
  id: string;
  tenant_id: string;
  business_name: string;
  connector_type_id: string;
  connector_type_key: string;
  status: ConnectorAccessRequestStatus;
  reason: string | null;
  requested_by: string;
  requested_by_email: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}
