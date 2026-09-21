/**
 * Hand-written types for the Instagram "Comment Automation" predefined
 * automation, mirroring the backend's `PredefinedAutomation` DTO
 * (`backend/src/fusionflow/modules/predefined_automations/...`) and this
 * automation type's `config` shape. Kept local to this feature - same
 * reasoning as `frontend/web/src/features/connectors/types.ts`.
 */

export type InstagramMatchingMethod = "exact" | "contains" | "starts_with" | "ends_with";

/** `config` for `automation_type: "instagram.comment_automation"`. */
export interface InstagramCommentAutomationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  auto_like: boolean;
  auto_hide: boolean;
  reply_comment_text: string | null;
  dm_text: string | null;
}

export interface PredefinedAutomation {
  id: string;
  connector_instance_id: string;
  automation_type: string;
  workflow_id: string | null;
  config: InstagramCommentAutomationConfig;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateInstagramAutomationPayload {
  connector_instance_id: string;
  name: string;
  config: InstagramCommentAutomationConfig;
}
