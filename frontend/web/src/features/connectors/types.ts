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
  | "dashboard";

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
 * Per-tenant entitlement for one connector type - "granted" (in the
 * tenant's business-template bundle, or an approved access request),
 * "pending" (access request awaiting admin review), "denied", or
 * "not_requested". Computed server-side in `GET /connectors/types` -
 * see `backend/.../connectors/service.py::get_connector_access_map`.
 */
export type ConnectorAccessStatus = "granted" | "pending" | "denied" | "not_requested";

export interface ConnectorType {
  id: string;
  key: string;
  category: ConnectorCategory;
  display_name: string;
  config_schema: Record<string, unknown>;
  oauth: boolean;
  is_enabled_globally: boolean;
  access_status: ConnectorAccessStatus;
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
