import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { File as FileIcon, ImageOff, Trash2 } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";
import { useConnectorInstances } from "../../../connectors/hooks";
import { ConfirmDialog } from "../../../connectors/components/ConfirmDialog";
import { useDeleteMediaAsset, useMediaAssets, useUploadMedia } from "../hooks";

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(1)} KB`;
  const mb = kb / 1024;
  return `${mb.toFixed(1)} MB`;
}

/**
 * `/communication/media-library` - catalog of uploaded media assets.
 * Uploading reuses the generic connector-instance-scoped media route
 * (`POST /api/v1/connectors/{instanceId}/media`), so it needs a connected
 * Cloudflare R2 instance to target; when the tenant has none, the upload
 * button is disabled with a pointer to `/connectors/cloudflare_r2/connect`
 * instead of duplicating that connect flow here.
 */
export function MediaLibraryPage() {
  const { data: assets, isLoading } = useMediaAssets();
  const { data: instances } = useConnectorInstances();
  const uploadMutation = useUploadMedia();
  const deleteMutation = useDeleteMediaAsset();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const r2Instance = (instances ?? []).find(
    (instance) => instance.connector_type_key === "cloudflare_r2" && instance.state === "connected",
  );

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !r2Instance) return;
    uploadMutation.mutate({ instanceId: r2Instance.id, file });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Media Library</h1>
          <p className="text-sm text-muted-foreground">Manage your media assets in one place.</p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Button
            onClick={() => fileInputRef.current?.click()}
            disabled={!r2Instance || uploadMutation.isPending}
          >
            {uploadMutation.isPending ? "Uploading…" : "+ Add New Media"}
          </Button>
          {!r2Instance && (
            <p className="text-xs text-muted-foreground">
              Connect{" "}
              <Link to="/connectors/cloudflare_r2/connect" className="text-accent underline-offset-4 hover:underline">
                Cloudflare R2
              </Link>{" "}
              first to upload media.
            </p>
          )}
          <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileChange} />
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading media…</p>
      ) : (assets ?? []).length === 0 ? (
        <Card>
          <CardHeader className="items-center text-center">
            <ImageOff className="mb-2 h-6 w-6 text-muted-foreground" />
            <CardTitle>No media found!</CardTitle>
            <CardDescription>Upload an image, video, or file to see it listed here.</CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Preview</TableHead>
                  <TableHead>Filename</TableHead>
                  <TableHead>Size</TableHead>
                  <TableHead>Uploaded</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(assets ?? []).map((asset) => (
                  <TableRow key={asset.id}>
                    <TableCell>
                      {asset.content_type.startsWith("image/") ? (
                        <img
                          src={asset.url}
                          alt={asset.filename}
                          className="h-10 w-10 rounded-md object-cover"
                        />
                      ) : (
                        <div className="flex h-10 w-10 items-center justify-center rounded-md bg-muted">
                          <FileIcon className="h-5 w-5 text-muted-foreground" />
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="max-w-xs truncate text-sm text-foreground">{asset.filename}</TableCell>
                    <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                      {formatSize(asset.size_bytes)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                      {new Date(asset.created_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" onClick={() => setPendingDeleteId(asset.id)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title="Delete this media asset?"
        description="This removes it from the catalog. The underlying stored file is not deleted."
        confirmLabel="Delete"
        destructive
        busy={deleteMutation.isPending}
        onCancel={() => setPendingDeleteId(null)}
        onConfirm={() => {
          if (!pendingDeleteId) return;
          deleteMutation.mutate(pendingDeleteId, {
            onSettled: () => setPendingDeleteId(null),
          });
        }}
      />
    </div>
  );
}
