import { useRef, useState, type ChangeEvent } from "react";
import { Link } from "react-router-dom";
import { isAxiosError } from "axios";
import { Loader2, Upload } from "lucide-react";
import { Button } from "@fusion-flow/ui";
import { uploadMedia } from "../api";

/**
 * Small "Upload a file" control for `whatsapp.send_message`'s Media/
 * Template config editors (`SendMessageContentField.tsx`'s `MediaEditor`
 * and its Template media-header counterpart) - an alternative to typing
 * a raw `media_url`/`media_id`. Uploads straight to the tenant's connected
 * `cloudflare_r2` storage instance via `uploadMedia` (`../api.ts`) and
 * reports the resulting public URL back through `onUploaded`.
 *
 * Deliberately stateless about *which* instance to use - the caller
 * resolves `connectorInstanceId` (e.g. via `useConnectorInstances()`
 * filtered to `connector_type_key === "cloudflare_r2"`, first connected
 * one) so this component stays a dumb, reusable "pick a file, upload it"
 * primitive usable from either media editor without duplicating that
 * lookup.
 */

interface MediaUploadButtonProps {
  /** The tenant's connected `cloudflare_r2` connector instance id. When
   * `undefined` (no storage integration connected yet), renders a
   * disabled hint linking to `/connectors` instead of the button - same
   * "no connected instance" messaging `NodeInlineForm.tsx` uses for
   * `suggested_select` fields. */
  connectorInstanceId: string | undefined;
  onUploaded: (url: string) => void;
}

export function MediaUploadButton({ connectorInstanceId, onUploaded }: MediaUploadButtonProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!connectorInstanceId) {
    return (
      <p className="text-[11px] text-muted-foreground">
        Connect a storage integration first — connect one in{" "}
        <Link to="/connectors" className="underline">
          Connectors
        </Link>
      </p>
    );
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    // Let the same file be re-selected later (e.g. after an error) by
    // clearing the input now rather than after the request settles.
    event.target.value = "";
    if (!file) return;

    setError(null);
    setUploading(true);
    try {
      const result = await uploadMedia(connectorInstanceId as string, file);
      onUploaded(result.url);
    } catch (err) {
      const message = isAxiosError<{ detail?: string }>(err)
        ? (err.response?.data?.detail ?? err.message)
        : "Upload failed. Try again.";
      setError(message);
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex flex-col gap-1">
      <input ref={inputRef} type="file" className="hidden" onChange={handleFileChange} disabled={uploading} />
      <Button
        type="button"
        variant="outline"
        size="sm"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
      >
        {uploading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
        {uploading ? "Uploading…" : "Upload a file"}
      </Button>
      {error && <p className="text-[11px] text-destructive">{error}</p>}
    </div>
  );
}
