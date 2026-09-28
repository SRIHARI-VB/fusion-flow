/**
 * Hand-written types mirroring the backend's connector framework DTOs
 * (`backend/src/fusionflow/modules/connectors/schemas.py`). Kept local to
 * this feature rather than added to `@fusion-flow/ts-types` - that package
 * is shared across `web`+`admin` and owned outside this feature's boundary
 * for this wave; promote these there once the OpenAPI generator covers
 * `/connectors/*` (see `frontend/packages/ts-types/README.md`).
 */

export type ConnectorCategory =
  | "messaging"
  | "payment"
  | "calendar"
  | "mail"
  | "support_agent"
  | "dashboard"
  | "feature"
  | "storage"
  | "social"
  | "video"
  | "spreadsheet";

/** Fixed lifecycle state machine - see the plan's "Connector Lifecycle Framework". */
export type ConnectorState =
  | "not_connected"
  | "connecting"
  | "connected"
  | "action_required"
  | "error"
  | "disconnected";

export type ConnectorHealthStatus = "healthy" | "degraded" | "down";

export type ConnectorEventType = "webhook_received" | "sync" | "oauth_callback" | "error";

/**
 * Per-tenant-and-role entitlement for one connector type - "granted" (in
 * the tenant's business-template bundle, or an approved access request),
 * "pending" (access request awaiting admin review), "denied", "restricted"
 * (the tenant has it, but an Owner/Admin blocked THIS caller's role from
 * it), or "not_requested". Computed server-side in `GET /connectors/types`
 * - see `backend/.../connectors/service.py::get_connector_access_map_for_role`.
 */
export type ConnectorAccessStatus = "granted" | "pending" | "denied" | "restricted" | "not_requested";

export interface ConnectorType {
  id: string;
  key: string;
  category: ConnectorCategory;
  display_name: string;
  config_schema: Record<string, unknown>;
  oauth: boolean;
  is_enabled_globally: boolean;
  access_status: ConnectorAccessStatus;
  // Static, tenant-independent webhook setup instructions (e.g. WhatsApp's
  // manual verify-token handshake) - null for a provider that doesn't need one.
  webhook_callback_url: string | null;
  webhook_verify_token: string | null;
}

export interface ConnectorAccessRequest {
  id: string;
  connector_type_id: string;
  connector_type_key: string;
  status: "pending" | "approved" | "denied";
  reason: string | null;
  requested_by: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

/**
 * NEVER extend this with a credential/secret field - the backend
 * guarantees `connector_credentials` is never selected into this DTO;
 * `connected_identity`/`provider_ref_ids` are the only identity-shaped
 * data it returns, and both are already adapter-redacted allowlists.
 */
export interface ConnectorInstance {
  id: string;
  connector_type_id: string;
  connector_type_key: string;
  connector_type_display_name: string;
  connector_category: ConnectorCategory;
  state: ConnectorState;
  display_name: string;
  connected_identity: Record<string, unknown> | null;
  health_status: ConnectorHealthStatus | null;
  last_webhook_at: string | null;
  last_sync_at: string | null;
  last_error_message: string | null;
  provider_ref_ids: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  disconnected_at: string | null;
}

export interface ConnectorEvent {
  id: string;
  connector_instance_id: string;
  event_type: ConnectorEventType;
  payload: Record<string, unknown>;
  occurred_at: string;
}

export interface ConnectRequest {
  display_name?: string;
  params?: Record<string, unknown>;
}

export interface ConnectResponse {
  instance: ConnectorInstance;
  redirect_url: string | null;
}

/** One row of the Settings "Team Permissions" table - a FEATURE module
 * this tenant has, with whether Member/Viewer are currently restricted. */
export interface ModuleRoleAccess {
  connector_type_id: string;
  key: string;
  display_name: string;
  member_restricted: boolean;
  viewer_restricted: boolean;
}

export type RestrictableRole = "member" | "viewer";

export interface SetRoleRestrictionRequest {
  connector_type_id: string;
  role: RestrictableRole;
  restricted: boolean;
}
