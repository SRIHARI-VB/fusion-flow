import type { ReactNode } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";

/**
 * A form-carrying overlay, same visual shell as `connectors/components/
 * ConfirmDialog.tsx` (fixed backdrop + centered Card, click-outside to
 * cancel) but with a real content slot - `ConfirmDialog` hardcodes an empty
 * `CardContent`, so it can't host the add-patient/assign-doctor/billing
 * forms this feature needs. Kept local to this feature (not added to the
 * shared `@fusion-flow/ui` package) for the same "deliberately small,
 * outside this feature's ownership boundary" reasoning `ConfirmDialog`'s
 * own docstring gives.
 */
export function Modal({
  open,
  title,
  description,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
}) {
  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <Card className="w-full max-w-md" onClick={(event) => event.stopPropagation()}>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent className="flex flex-col gap-4">{children}</CardContent>
      </Card>
    </div>
  );
}
