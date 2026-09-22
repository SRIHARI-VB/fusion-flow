/**
 * Hand-written types mirroring the backend's broadcast-campaign DTOs
 * (`backend/src/fusionflow/modules/.../broadcast_campaigns` schemas -
 * see this feature's task spec). Campaigns are WhatsApp-only, one-off
 * sends: there is no recurrence field and no PATCH/update endpoint -
 * a campaign is immutable after creation (delete and recreate to
 * change anything), matching this codebase's established convention
 * for similarly immutable resources (e.g. `custom_fields`'s
 * `FieldDefinitionUpdate` docstring).
 */

export type BroadcastCampaignLastRunStatus = "success" | "partial_failure" | "failed" | string;

export interface BroadcastCampaign {
  id: string;
  connector_instance_id: string;
  name: string;
  message_text: string;
  recipient_phone_numbers: string[];
  media_url: string | null;
  media_type: string | null;
  location_latitude: number | null;
  location_longitude: number | null;
  location_name: string | null;
  location_address: string | null;
  workflow_id: string;
  created_at: string;
  updated_at: string;
  next_run_at: string | null;
  is_active: boolean;
  last_run_at: string | null;
  last_run_status: BroadcastCampaignLastRunStatus | null;
}

export interface CreateBroadcastCampaignPayload {
  connector_instance_id: string;
  name: string;
  message_text: string;
  recipient_phone_numbers: string[];
  scheduled_at: string;
  media_url: string | null;
  media_type: string | null;
  location_latitude: number | null;
  location_longitude: number | null;
  location_name: string | null;
  location_address: string | null;
}
