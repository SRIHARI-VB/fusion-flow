/**
 * Hand-written type mirroring the backend's media asset catalog DTO
 * (`GET /api/v1/media-assets`). Kept local to this feature rather than
 * added to `@fusion-flow/ts-types` for the same reason `features/connectors`
 * keeps its own `types.ts` - that package is shared across `web`+`admin`
 * and owned outside this feature's boundary for this wave.
 */
export interface MediaAsset {
  id: string;
  url: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  source: string;
  created_at: string;
}
