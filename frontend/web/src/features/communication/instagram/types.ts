/**
 * Hand-written types for Instagram's predefined automations, mirroring the
 * backend's `PredefinedAutomation` DTO
 * (`backend/src/fusionflow/modules/predefined_automations/...`) and each
 * registered automation type's `config` shape. Kept local to this feature -
 * same reasoning as `frontend/web/src/features/connectors/types.ts`.
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

/** `config` for `automation_type: "instagram.dm_automation"`. */
export interface InstagramDmAutomationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  reply_text: string;
}

export type InstagramAutomationConfig = InstagramCommentAutomationConfig | InstagramDmAutomationConfig;

export interface PredefinedAutomation {
  id: string;
  connector_instance_id: string;
  automation_type: string;
  workflow_id: string | null;
  config: InstagramAutomationConfig;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

/** Narrows `PredefinedAutomation.config` by `automation_type` - every
 * config shape here happens to share `trigger_keywords`/`matching_method`,
 * but only a comment automation has `auto_like`/`auto_hide`/
 * `reply_comment_text`/`dm_text`. */
export function isCommentAutomationConfig(
  automation: PredefinedAutomation,
): automation is PredefinedAutomation & { config: InstagramCommentAutomationConfig } {
  return automation.automation_type === "instagram.comment_automation";
}

export interface CreateInstagramAutomationPayload {
  connector_instance_id: string;
  automation_type: string;
  name: string;
  config: InstagramAutomationConfig;
}
