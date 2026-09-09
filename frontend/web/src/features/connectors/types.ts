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

export interface ConnectorType {
  id: string;
  key: string;
  category: ConnectorCategory;
  display_name: string;
  config_schema: Record<string, unknown>;
  oauth: boolean;
  is_enabled_globally: boolean;
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
