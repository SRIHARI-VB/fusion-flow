import { FileText, MapPin, Play, Volume2 } from "lucide-react";
import { cn } from "@fusion-flow/ui";

/**
 * Small, read-only visual previews for `whatsapp.send_message`'s media/
 * location content - used both by `SendMessageContentField.tsx`'s editors
 * (immediate feedback right after an upload/URL/coordinate is entered) and
 * by `nodes/NodePreview.tsx`'s collapsed bubble (`size="sm"` everywhere
 * there vs `size="md"` in the editor). Two exports:
 *
 * - `MediaThumb` - image/video/audio/document, dispatched by `mediaType`.
 * - `LocationPreview` - a real small OpenStreetMap tile (no API key - see
 *   this feature's plan for why every free "static map + marker" service
 *   is dead, and why hand-rolling the slippy-map tile/pixel math below
 *   against OSM's own raw tile server is the sanctioned way to do this
 *   client-side) with a `MapPin` positioned at the exact point, plus the
 *   attribution OSM's tile usage policy requires.
 */

export type MediaKind = "image" | "video" | "audio" | "document";

interface MediaThumbProps {
  mediaType: MediaKind;
  url?: string;
  mediaId?: string;
  filename?: string;
  size?: "sm" | "md";
}

const BOX_SIZE_CLASS: Record<"sm" | "md", string> = { sm: "h-16 w-16", md: "h-24 w-24" };

function filenameFromUrl(url: string): string {
  try {
    const path = new URL(url).pathname;
    const last = path.split("/").filter(Boolean).pop();
    return last ? decodeURIComponent(last) : "Document";
  } catch {
    const last = url.split("/").filter(Boolean).pop();
    return last || "Document";
  }
}

function DocumentPill({ label }: { label: string }) {
  return (
    <span className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1 text-[11px] text-foreground">
      <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate">{label}</span>
    </span>
  );
}

export function MediaThumb({ mediaType, url, mediaId, filename, size = "md" }: MediaThumbProps) {
  const box = BOX_SIZE_CLASS[size];

  // A hand-typed `media_id` with no URL is opaque (a WhatsApp-side upload
  // reference) - nothing to fetch, so no attempt at a real thumbnail.
  if (!url) {
    if (!mediaId) return null;
    return <p className="text-[11px] italic text-muted-foreground">Uploaded media (no direct preview)</p>;
  }

  if (mediaType === "image") {
    return <img src={url} alt="" className={cn(box, "rounded-md border border-border object-cover")} />;
  }

  if (mediaType === "video") {
    return (
      <div className={cn(box, "relative overflow-hidden rounded-md border border-border bg-muted")}>
        <video
          src={url}
          muted
          preload="metadata"
          controls={size === "md"}
          className="h-full w-full object-cover"
        />
        {size === "sm" && (
          <span className="pointer-events-none absolute inset-0 flex items-center justify-center bg-black/20">
            <Play className="h-5 w-5 fill-white text-white" />
          </span>
        )}
      </div>
    );
  }

  if (mediaType === "audio") {
    if (size === "sm") {
      return (
        <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-card px-2 py-1 text-[11px] text-foreground">
          <Volume2 className="h-3.5 w-3.5 text-muted-foreground" /> Audio message
        </span>
      );
    }
    return <audio src={url} controls className="h-8 w-full max-w-[220px]" />;
  }

  // document
  return <DocumentPill label={filename || filenameFromUrl(url)} />;
}

const TILE_SIZE = 256;
const DEFAULT_ZOOM = 15;
const BOX_PX: Record<"sm" | "md", number> = { sm: 96, md: 160 };

function lonToTileX(lon: number, zoom: number): number {
  return Math.floor(((lon + 180) / 360) * 2 ** zoom);
}
function latToTileY(lat: number, zoom: number): number {
  const latRad = (lat * Math.PI) / 180;
  return Math.floor(((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * 2 ** zoom);
}
function lonToPixelX(lon: number, zoom: number): number {
  return ((lon + 180) / 360) * 2 ** zoom * TILE_SIZE;
}
function latToPixelY(lat: number, zoom: number): number {
  const latRad = (lat * Math.PI) / 180;
  return ((1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2) * 2 ** zoom * TILE_SIZE;
}

interface LocationPreviewProps {
  latitude: number;
  longitude: number;
  name?: string;
  address?: string;
  size?: "sm" | "md";
}

/** `latitude === 0 && longitude === 0` is `DEFAULT_LOCATION_CONTENT`'s
 * untouched sentinel (the Gulf of Guinea) - callers that want to skip the
 * map entirely for an unconfigured node (e.g. the collapsed bubble, which
 * falls back to its own generic empty-state placeholder) should check this
 * before rendering `LocationPreview`, not after. */
export function isUnsetLocation(latitude: number, longitude: number): boolean {
  return latitude === 0 && longitude === 0;
}

export function LocationPreview({ latitude, longitude, name, address, size = "md" }: LocationPreviewProps) {
  if (isUnsetLocation(latitude, longitude)) {
    return <p className="text-[11px] italic text-muted-foreground">Set coordinates above to preview the location.</p>;
  }

  const boxPx = BOX_PX[size];
  const scale = boxPx / TILE_SIZE;
  const tileX = lonToTileX(longitude, DEFAULT_ZOOM);
  const tileY = latToTileY(latitude, DEFAULT_ZOOM);
  const pinLeft = (lonToPixelX(longitude, DEFAULT_ZOOM) - tileX * TILE_SIZE) * scale;
  const pinTop = (latToPixelY(latitude, DEFAULT_ZOOM) - tileY * TILE_SIZE) * scale;
  const tileUrl = `https://tile.openstreetmap.org/${DEFAULT_ZOOM}/${tileX}/${tileY}.png`;
  const label = name || address;

  return (
    <div className="flex flex-col gap-1">
      <div
        className="relative overflow-hidden rounded-md border border-border bg-muted"
        style={{ width: boxPx, height: boxPx }}
      >
        <img src={tileUrl} alt="" className="h-full w-full object-cover" />
        <MapPin
          className="pointer-events-none absolute h-5 w-5 text-destructive"
          fill="currentColor"
          style={{ left: pinLeft, top: pinTop, transform: "translate(-50%, -100%)" }}
        />
      </div>
      {label && <p className="max-w-[160px] truncate text-[11px] text-muted-foreground">{label}</p>}
      <a
        href="https://www.openstreetmap.org/copyright"
        target="_blank"
        rel="noreferrer"
        className="nodrag text-[9px] text-muted-foreground underline"
      >
        © OpenStreetMap contributors
      </a>
    </div>
  );
}
