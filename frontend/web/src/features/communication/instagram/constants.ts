import type { InstagramMatchingMethod } from "./types";

/** Backend automation type keys for `POST /api/v1/predefined-automations`. */
export const INSTAGRAM_COMMENT_AUTOMATION_TYPE = "instagram.comment_automation";
export const INSTAGRAM_DM_AUTOMATION_TYPE = "instagram.dm_automation";

/** Short label - used in the automations table. */
export const MATCHING_METHOD_LABELS: Record<InstagramMatchingMethod, string> = {
  exact: "Exact Match",
  contains: "Contains",
  starts_with: "Starts With",
  ends_with: "Ends With",
};

/** One-line explanation - used by the wizard's `OptionPickerCard`s. */
export const MATCHING_METHOD_DESCRIPTIONS: Record<InstagramMatchingMethod, string> = {
  exact: "Keyword must match exactly",
  contains: "Message must contain the keyword",
  starts_with: "Message must start with keyword",
  ends_with: "Message must end with keyword",
};

export const MATCHING_METHODS: InstagramMatchingMethod[] = ["exact", "contains", "starts_with", "ends_with"];
