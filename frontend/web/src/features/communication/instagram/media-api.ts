import { apiClient } from "../../../lib/api-client";

/**
 * Talks to `/api/v1/connectors/{instance_id}/instagram/media` - this
 * account's own posts/reels, used by Comment Automation/Comment
 * Moderation's "scope to specific posts/reels" picker. Deliberately kept
 * separate from `api.ts` (scoped to `PredefinedAutomation` CRUD) and
 * `ice-breakers-api.ts` (a different connector-instance-level settings
 * blob) - same "own router, own tiny client file" convention.
 *
 * Paginated (Meta's own `after` cursor) rather than one flat list - an
 * account with hundreds of posts/reels can't be handed back in one
 * response. `fetchInstagramMediaPage` is the raw paged call; the picker
 * UI drives it via a "Load more" button, one page at a time.
 */

export interface InstagramMedia {
  id: string;
  media_type: string;
  caption: string | null;
  media_url: string | null;
  thumbnail_url: string | null;
  permalink: string | null;
  timestamp: string | null;
}

export interface InstagramMediaPage {
  items: InstagramMedia[];
  next_cursor: string | null;
}

export async function fetchInstagramMediaPage(
  instanceId: string,
  options: { after?: string | null; limit?: number } = {},
): Promise<InstagramMediaPage> {
  const { data } = await apiClient.get<InstagramMediaPage>(
    `/api/v1/connectors/${instanceId}/instagram/media`,
    { params: { after: options.after ?? undefined, limit: options.limit ?? 25 } },
  );
  return data;
}
