import { useState } from "react";
import { useForm } from "react-hook-form";
import { MessageSquareText, Pencil, Plus, Trash2, X } from "lucide-react";
import {
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Textarea,
} from "@fusion-flow/ui";
import { ConfirmDialog } from "../../../connectors/components/ConfirmDialog";
import { useCreateQuickReply, useDeleteQuickReply, useQuickReplies, useUpdateQuickReply } from "../hooks";
import type { QuickReply } from "../types";

interface FormValues {
  title: string;
  body: string;
}

const DEFAULT_VALUES: FormValues = { title: "", body: "" };

const BODY_PREVIEW_LENGTH = 80;

function previewBody(body: string): string {
  if (body.length <= BODY_PREVIEW_LENGTH) return body;
  return `${body.slice(0, BODY_PREVIEW_LENGTH).trimEnd()}…`;
}

/**
 * `/communication/quick-replies` — CRUD list of reusable text snippets a
 * team can paste into any conversation. Mirrors this codebase's other
 * simple settings CRUD pages (see `CustomFieldsSettingsPage`): an inline
 * create/edit `Card` form above a `Table` of existing rows, with delete
 * always behind the shared `ConfirmDialog` (per the connectors feature's
 * "destructive actions behind a confirm dialog" convention).
 */
export function QuickRepliesPage() {
  const { data: quickReplies = [], isLoading } = useQuickReplies();
  const createMutation = useCreateQuickReply();
  const updateMutation = useUpdateQuickReply();
  const deleteMutation = useDeleteQuickReply();

  const [editing, setEditing] = useState<QuickReply | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ defaultValues: DEFAULT_VALUES });

  function openCreateForm() {
    setEditing(null);
    reset(DEFAULT_VALUES);
    setFormOpen(true);
  }

  function openEditForm(quickReply: QuickReply) {
    setEditing(quickReply);
    reset({ title: quickReply.title, body: quickReply.body });
    setFormOpen(true);
  }

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
  }

  function onSubmit(values: FormValues) {
    if (editing) {
      updateMutation.mutate(
        { id: editing.id, payload: values },
        { onSuccess: closeForm },
      );
    } else {
      createMutation.mutate(values, { onSuccess: closeForm });
    }
  }

  const saving = createMutation.isPending || updateMutation.isPending;
  const pendingDelete = quickReplies.find((qr) => qr.id === pendingDeleteId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-row items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Quick Replies</h1>
          <p className="text-sm text-muted-foreground">
            Reusable snippets your team can paste into any conversation.
          </p>
        </div>
        <Button onClick={openCreateForm}>
          <Plus className="mr-2 h-4 w-4" /> New Quick Reply
        </Button>
      </div>

      {formOpen && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>{editing ? `Edit "${editing.title}"` : "New quick reply"}</CardTitle>
            <Button variant="ghost" size="sm" onClick={closeForm}>
              <X className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent>
            <form className="flex flex-col gap-4" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="title" className="text-sm font-medium">
                  Title
                </label>
                <Input
                  id="title"
                  placeholder="Order status update"
                  error={!!errors.title}
                  {...register("title", { required: "Title is required" })}
                />
                {errors.title && <p className="text-xs text-destructive">{errors.title.message}</p>}
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="body" className="text-sm font-medium">
                  Body
                </label>
                <Textarea
                  id="body"
                  rows={4}
                  placeholder="Hi! Your order is on its way and should arrive within..."
                  {...register("body", { required: "Body is required" })}
                />
                {errors.body && <p className="text-xs text-destructive">{errors.body.message}</p>}
              </div>

              {(createMutation.isError || updateMutation.isError) && (
                <p className="text-sm text-destructive">
                  Could not save this quick reply. Please try again.
                </p>
              )}

              <div className="flex gap-2">
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving..." : editing ? "Save changes" : "Create quick reply"}
                </Button>
                <Button type="button" variant="ghost" onClick={closeForm}>
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>All quick replies</CardTitle>
          <CardDescription>Available to paste into any conversation across every channel.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}

          {!isLoading && quickReplies.length === 0 && (
            <div className="flex flex-col items-center gap-2 py-10 text-center">
              <MessageSquareText className="h-8 w-8 text-muted-foreground" />
              <p className="text-sm font-medium text-foreground">No quick replies yet</p>
              <p className="text-sm text-muted-foreground">
                Create reusable snippets your team can paste into any conversation.
              </p>
              <Button className="mt-2" onClick={openCreateForm}>
                <Plus className="mr-2 h-4 w-4" /> New Quick Reply
              </Button>
            </div>
          )}

          {!isLoading && quickReplies.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Body</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {quickReplies.map((quickReply) => (
                  <TableRow key={quickReply.id}>
                    <TableCell className="font-medium">{quickReply.title}</TableCell>
                    <TableCell className="text-muted-foreground">{previewBody(quickReply.body)}</TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="sm" onClick={() => openEditForm(quickReply)}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setPendingDeleteId(quickReply.id)}>
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={`Delete "${pendingDelete?.title ?? "this quick reply"}"?`}
        description="This snippet will no longer be available to paste into conversations. This cannot be undone."
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
