import { useRef, useState, type ChangeEvent } from "react";
import { isAxiosError } from "axios";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Upload, X } from "lucide-react";
import { Button, Card, CardContent } from "@fusion-flow/ui";
import { useConnectorInstances } from "../../connectors/hooks";
import { fetchMediaAssets, uploadMedia } from "../media-library/api";

export interface SelectedMedia {
  url: string;
  content_type: string;
}

interface MediaPickerProps {
  value: SelectedMedia | null;
  onChange: (media: SelectedMedia | null) => void;
  /** Restricts the "pick from library" grid and the accepted file input
   * to one media family - most Instagram send actions only support image
   * or video attachments, never arbitrary documents. */
  accept?: "image" | "video" | "image,video";
}

/**
 * Reusable "attach a media file" control for any wizard step that wants
 * to optionally send an image/video alongside (or instead of) text -
 * DM/story-reply/button-menu automations, and anywhere else predefined
 * automations grow a media-capable action. Two ways in, same output
 * shape (`{url, content_type}`, directly usable as `instagram.
 * send_media_message`'s `params.media_url`):
 *
 * - "Upload new": reuses the existing Cloudflare R2 upload path
 *   (`media-library/api.ts::uploadMedia`, the same one `frontend/web/src/
 *   features/workflows/components/MediaUploadButton.tsx` already
 *   established) - requires a connected `cloudflare_r2` storage
 *   integration, same precondition that component documents.
 * - "Choose from library": lists already-uploaded assets
 *   (`GET /api/v1/media-assets`) as a small thumbnail grid to pick from,
 *   without uploading anything new.
 */
export function MediaPicker({ value, onChange, accept = "image,video" }: MediaPickerProps) {
  const { data: instances } = useConnectorInstances();
  const storageInstance = (instances ?? []).find(
    (instance) => instance.connector_type_key === "cloudflare_r2" && instance.state === "connected",
  );

  const [mode, setMode] = useState<"upload" | "library" | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const { data: libraryAssets, isLoading: libraryLoading } = useQuery({
    queryKey: ["media-assets"],
    queryFn: fetchMediaAssets,
    enabled: mode === "library",
  });

  const acceptAttr =
    accept === "image" ? "image/*" : accept === "video" ? "video/*" : "image/*,video/*";

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !storageInstance) return;

    setError(null);
    setUploading(true);
    try {
      const result = await uploadMedia(storageInstance.id, file);
      onChange({ url: result.url, content_type: file.type || "application/octet-stream" });
      setMode(null);
    } catch (err) {
      const message = isAxiosError<{ detail?: string }>(err)
        ? (err.response?.data?.detail ?? err.message)
        : "Upload failed. Try again.";
      setError(message);
    } finally {
      setUploading(false);
    }
  }

  if (value) {
    return (
      <div className="flex items-center gap-2 rounded-md border border-border bg-card p-2">
        {value.content_type.startsWith("video") ? (
          <video src={value.url} muted className="h-14 w-14 rounded object-cover" />
        ) : (
          <img src={value.url} alt="" className="h-14 w-14 rounded object-cover" />
        )}
        <span className="flex-1 truncate text-xs text-muted-foreground">{value.url}</span>
        <Button type="button" variant="outline" size="sm" onClick={() => onChange(null)}>
          <X className="h-3.5 w-3.5" />
          Remove
        </Button>
      </div>
    );
  }

  if (mode === null) {
    return (
      <div className="flex gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => setMode("upload")}>
          <Upload className="h-3.5 w-3.5" />
          Upload a file
        </Button>
        <Button type="button" variant="outline" size="sm" onClick={() => setMode("library")}>
          Choose from library
        </Button>
      </div>
    );
  }

  if (mode === "upload") {
    if (!storageInstance) {
      return (
        <Card>
          <CardContent className="flex flex-col gap-2 pt-4 text-sm">
            <p className="text-muted-foreground">
              Connect a storage integration first (Connectors → Cloudflare R2) before uploading media.
            </p>
            <Button type="button" variant="outline" size="sm" onClick={() => setMode(null)}>
              Back
            </Button>
          </CardContent>
        </Card>
      );
    }
    return (
      <div className="flex flex-col gap-2">
        <input ref={inputRef} type="file" accept={acceptAttr} className="hidden" onChange={handleFileChange} disabled={uploading} />
        <div className="flex gap-2">
          <Button type="button" variant="outline" size="sm" disabled={uploading} onClick={() => inputRef.current?.click()}>
            {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            {uploading ? "Uploading…" : "Select a file"}
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => setMode(null)} disabled={uploading}>
            Cancel
          </Button>
        </div>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    );
  }

  const filteredAssets = (libraryAssets ?? []).filter((asset) =>
    accept === "image,video" ? true : asset.content_type.startsWith(accept),
  );

  return (
    <div className="flex flex-col gap-2">
      {libraryLoading ? (
        <p className="text-xs text-muted-foreground">Loading media library…</p>
      ) : filteredAssets.length === 0 ? (
        <p className="text-xs text-muted-foreground">No media uploaded yet.</p>
      ) : (
        <div className="grid grid-cols-4 gap-2">
          {filteredAssets.map((asset) => (
            <button
              key={asset.id}
              type="button"
              className="overflow-hidden rounded-md border border-border hover:border-accent"
              onClick={() => {
                onChange({ url: asset.url, content_type: asset.content_type });
                setMode(null);
              }}
            >
              {asset.content_type.startsWith("video") ? (
                <video src={asset.url} muted className="h-16 w-16 object-cover" />
              ) : (
                <img src={asset.url} alt={asset.filename} className="h-16 w-16 object-cover" />
              )}
            </button>
          ))}
        </div>
      )}
      <Button type="button" variant="outline" size="sm" onClick={() => setMode(null)} className="w-fit">
        Cancel
      </Button>
    </div>
  );
}
