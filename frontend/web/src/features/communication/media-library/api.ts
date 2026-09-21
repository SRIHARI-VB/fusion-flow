import { apiClient } from "../../../lib/api-client";
import type { MediaAsset } from "./types";

/**
 * Talks to the media asset catalog routes
 * (`backend/src/fusionflow/modules/media_assets` per the plan). The upload
 * call reuses the generic connector-instance-scoped media route
 * (`/api/v1/connectors/{instanceId}/media`) - see
 * `frontend/web/src/features/workflows/api.ts`'s `uploadMedia` for the
 * same pattern already established there. Uploading has a backend side
 * effect of inserting a `media_assets` row, so callers just refetch
 * `fetchMediaAssets()` afterwards rather than POSTing to it directly.
 */

export async function fetchMediaAssets(): Promise<MediaAsset[]> {
  const { data } = await apiClient.get<MediaAsset[]>("/api/v1/media-assets");
  return data;
}

export async function deleteMediaAsset(id: string): Promise<void> {
  await apiClient.delete(`/api/v1/media-assets/${id}`);
}

/**
 * `apiClient` infers the `multipart/form-data` Content-Type (with
 * boundary) from the `FormData` body on its own - don't set it manually.
 */
export async function uploadMedia(instanceId: string, file: File): Promise<{ url: string }> {
  const formData = new FormData();
  formData.append("file", file);
  const { data } = await apiClient.post<{ url: string }>(
    `/api/v1/connectors/${instanceId}/media`,
    formData,
  );
  return data;
}
