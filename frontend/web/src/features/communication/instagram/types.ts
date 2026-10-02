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

/** A single tappable button for `InstagramButtonMenuAutomationConfig` -
 * mirrors the backend's `ButtonConfig` Pydantic model
 * (`instagram_button_menu_automation.py`). `media_url`/`media_type` are
 * both `null` when no image/video is attached to that button's reply. */
export interface InstagramMenuButton {
  title: string;
  reply_text: string;
  media_url: string | null;
  media_type: string | null;
}

/** `config` for `automation_type: "instagram.button_menu_automation"`. */
export interface InstagramButtonMenuAutomationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  menu_text: string;
  buttons: InstagramMenuButton[];
  react_emoji: string | null;
}

/** `config` for `automation_type: "instagram.handoff_automation"`. */
export interface InstagramHandoffAutomationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  ack_text: string;
  react_emoji: string | null;
  auto_resume_after_hours: number | null;
}

export type InstagramReactionType = "love" | "like" | "laugh" | "wow" | "sad" | "angry";

/** `config` for `automation_type: "instagram.reaction_automation"`. */
export interface InstagramReactionAutomationConfig {
  reaction_type: InstagramReactionType;
  reply_text: string;
}

/** `config` for `automation_type: "instagram.comment_moderation"` - purely
 * a filtering automation (hide/delete), unlike
 * `InstagramCommentAutomationConfig` which is about replying. */
export interface InstagramCommentModerationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  hide: boolean;
  delete: boolean;
  media_ids: string[];
}

/** A single rule row for `InstagramReferralAutomationConfig` - mirrors the
 * backend's `ReferralRule` Pydantic model
 * (`instagram_referral_automation.py`). */
export interface InstagramReferralRule {
  ref_match: string;
  reply_text: string;
}

/** `config` for `automation_type: "instagram.referral_automation"`. */
export interface InstagramReferralAutomationConfig {
  rules: InstagramReferralRule[];
  default_reply_text: string | null;
}

/** `config` for `automation_type: "instagram.mention_automation"`. */
export interface InstagramMentionAutomationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  reply_text: string;
  reply_delay_minutes: number | null;
}

/** `config` for `automation_type: "instagram.story_reply_automation"`. */
export interface InstagramStoryReplyAutomationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  reply_text: string;
  media_url: string | null;
  media_type: string | null;
  react_emoji: string | null;
  reply_delay_minutes: number | null;
}

/** A single plain-text/media reply option for
 * `InstagramCommentMenuAutomationConfig` - mirrors the backend's
 * `MenuOption` Pydantic model (`instagram_comment_menu_automation.py`). */
export interface InstagramCommentMenuOption {
  keyword: string;
  reply_text: string;
  media_url: string | null;
  media_type: string | null;
}

/** `config` for `automation_type: "instagram.comment_menu_automation"` - a
 * comment-triggered Private Reply (text-only, reaches a first-time
 * commenter) that hands off to a DM-triggered keyword menu; one menu
 * option creates a support ticket instead of replying with text. */
export interface InstagramCommentMenuAutomationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  media_ids: string[];
  reply_comment_text: string | null;
  private_reply_text: string;
  menu_matching_method: InstagramMatchingMethod;
  menu_options: InstagramCommentMenuOption[];
  ticket_keyword: string;
  ticket_subject: string;
  ticket_confirmation_text: string;
}

export type InstagramAutomationConfig =
  | InstagramCommentAutomationConfig
  | InstagramDmAutomationConfig
  | InstagramButtonMenuAutomationConfig
  | InstagramHandoffAutomationConfig
  | InstagramReactionAutomationConfig
  | InstagramCommentModerationConfig
  | InstagramReferralAutomationConfig
  | InstagramMentionAutomationConfig
  | InstagramStoryReplyAutomationConfig
  | InstagramCommentMenuAutomationConfig;

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
