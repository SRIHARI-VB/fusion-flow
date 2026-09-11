import { Button } from "@fusion-flow/ui";

/**
 * Confirmation dialog before permanently deleting a workflow
 * (`WorkflowsListPage.tsx`). Same hand-rolled overlay convention as
 * `SaveComponentDialog.tsx`/`ComponentPicker.tsx` (no `Dialog`/`Modal`
 * primitive exists in `@fusion-flow/ui`) — `fixed inset-0` here instead of
 * their `absolute` positioning since this page has no relative canvas
 * wrapper to anchor to, so it needs to cover the whole viewport itself.
 */

interface DeleteWorkflowDialogProps {
  workflowName: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting?: boolean;
}

export function DeleteWorkflowDialog({ workflowName, onConfirm, onCancel, isDeleting }: DeleteWorkflowDialogProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-sm rounded-lg border border-border bg-card p-4 shadow-lg">
        <p className="text-sm font-semibold text-foreground">Delete workflow?</p>
        <p className="mt-2 text-sm text-muted-foreground">
          This will permanently delete <span className="font-medium text-foreground">"{workflowName}"</span> and
          all its versions and run history. This can't be undone.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onCancel} disabled={isDeleting}>
            Cancel
          </Button>
          <Button type="button" variant="destructive" size="sm" onClick={onConfirm} disabled={isDeleting}>
            {isDeleting ? "Deleting..." : "Delete"}
          </Button>
        </div>
      </div>
    </div>
  );
}
