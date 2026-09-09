import { Button, Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@fusion-flow/ui";

/**
 * Minimal confirm dialog composed entirely from `@fusion-flow/ui` primitives
 * (`Card`/`Button`) - the shared package has no `Dialog` component yet, so
 * this is a local, deliberately small overlay rather than adding one to a
 * package outside this feature's ownership boundary for this wave.
 *
 * Required before every `disconnect` call per the plan's connector
 * lifecycle framework ("disconnect always behind a confirm dialog").
 */
interface ConfirmDialogProps {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  busy = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onCancel}
    >
      <Card className="w-full max-w-sm" onClick={(event) => event.stopPropagation()}>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent />
        <CardFooter className="justify-end gap-2">
          <Button variant="outline" onClick={onCancel} disabled={busy}>
            {cancelLabel}
          </Button>
          <Button variant={destructive ? "destructive" : "default"} onClick={onConfirm} disabled={busy}>
            {busy ? "Working…" : confirmLabel}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
