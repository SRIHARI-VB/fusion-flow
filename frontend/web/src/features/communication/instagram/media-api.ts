import { apiClient } from "../../../lib/api-client";

/**
 * Talks to `/api/v1/connectors/{instance_id}/instagram/media` - this
 * account's own posts/reels, used by Comment Automation's "scope to one
 * post/reel" picker (see `pages/InstagramAutomationWizardPage.tsx`).
 * Deliberately kept separate from `api.ts` (scoped to `PredefinedAutomation`
 * CRUD) and `ice-breakers-api.ts` (a different connector-instance-level
 * settings blob) - same "own router, own tiny client file" convention.
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

export async function fetchInstagramMedia(instanceId: string): Promise<InstagramMedia[]> {
  const { data } = await apiClient.get<InstagramMedia[]>(`/api/v1/connectors/${instanceId}/instagram/media`);
  return data;
}
