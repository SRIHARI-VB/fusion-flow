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

/** One catalog row's resolved access for one tenant - drives the admin's
 * per-tenant "Modules & connectors" revoke/grant panel. */
export interface TenantModuleAccess {
  connector_type_id: string;
  connector_type_key: string;
  display_name: string;
  category: string;
  access_status: "granted" | "pending" | "denied" | "not_requested";
  has_override: boolean;
  override_granted: boolean | null;
}

export interface ConnectorAccessOverride {
  id: string;
  tenant_id: string;
  connector_type_id: string;
  granted: boolean;
  set_by: string | null;
  reason: string | null;
  created_at: string;
  updated_at: string;
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

/** One catalog resource key + this plan's configured limit (`null` =
 * unlimited at the plan level). Always one entry per catalog key, even if
 * unconfigured, so the editor can show an input for every resource. */
export interface PlanResourceLimit {
  connector_type_id: string;
  resource_key: string;
  display_name: string;
  max_count: number | null;
}

export interface TenantResourceLimit {
  connector_type_id: string;
  resource_key: string;
  display_name: string;
  limit: number | null;
  source: "tenant_override" | "plan" | "unlimited";
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

// Mirrors backend/src/fusionflow/modules/admin/schemas.py's
// WorkflowNodeTemplate* DTOs - the "new integration without a deploy"
// admin catalog on top of the workflow engine's generic executors
// (connector.action, http.request, ...). See modules.admin.models.
// WorkflowNodeTemplate's docstring for the full picture.
export interface WorkflowNodeTemplate {
  id: string;
  key: string;
  label: string;
  description: string | null;
  category: string;
  base_node_type: string;
  icon: string | null;
  default_config: Record<string, unknown>;
  config_schema_overrides: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
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
  /** The tenant's current status - "pending_approval" means this request
   * was filed as part of a brand-new signup application, not a later
   * additional request from an already-active tenant. */
  business_status: BusinessStatus;
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
