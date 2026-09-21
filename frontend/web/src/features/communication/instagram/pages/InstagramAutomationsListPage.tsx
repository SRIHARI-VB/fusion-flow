import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronDown, Instagram, MessageCircle, MessageSquare, Pencil, Plus, Trash2 } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";
import { Switch } from "../../wizard";
import { ConfirmDialog } from "../../../connectors/components/ConfirmDialog";
import { useDeleteInstagramAutomation, useInstagramAutomations, useSetInstagramAutomationActive } from "../hooks";
import { MATCHING_METHOD_LABELS } from "../constants";
import { isCommentAutomationConfig, type PredefinedAutomation } from "../types";

function automationTypeLabel(automation: PredefinedAutomation): string {
  return isCommentAutomationConfig(automation) ? "Comment Automation" : "DM Auto-Reply";
}

function editPathFor(automation: PredefinedAutomation): string {
  return isCommentAutomationConfig(automation)
    ? `/communication/instagram/automations/${automation.id}/edit`
    : `/communication/instagram/dm-automations/${automation.id}/edit`;
}

/**
 * `/communication/instagram/automations` - list of every predefined
 * automation configured against the tenant's connected Instagram account,
 * across both automation types ("Comment Automation" and "DM
 * Auto-Reply"). There is no `name` field on the backend's
 * `PredefinedAutomation` DTO, so the trigger keywords stand in as the
 * row's label (matches the spec: "config.trigger_keywords.join(', ')").
 */
export function InstagramAutomationsListPage() {
  const navigate = useNavigate();
  const { data: automations, isLoading } = useInstagramAutomations();
  const setActiveMutation = useSetInstagramAutomationActive();
  const deleteMutation = useDeleteInstagramAutomation();
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const pendingAutomation = automations?.find((automation) => automation.id === pendingDeleteId);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Instagram Automations</h1>
          <p className="text-sm text-muted-foreground">
            Automatically like, hide, or reply to comments - or auto-reply to direct messages - on this account.
          </p>
        </div>
        <DropdownMenu>
          <DropdownMenuTrigger>
            <Button variant="success">
              <Plus className="h-4 w-4" />
              New Automation
              <ChevronDown className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => navigate("/communication/instagram/automations/new")}>
              <MessageSquare className="h-3.5 w-3.5" />
              Comment Automation
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => navigate("/communication/instagram/dm-automations/new")}>
              <MessageCircle className="h-3.5 w-3.5" />
              DM Auto-Reply
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading automations…</p>
      ) : !automations || automations.length === 0 ? (
        <Card>
          <CardHeader className="items-center text-center">
            <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft text-accent">
              <Instagram className="h-6 w-6" />
            </div>
            <CardTitle>No automations yet</CardTitle>
            <CardDescription>
              Create a comment automation to auto-like, auto-hide, or reply to comments, or a DM auto-reply to
              respond to direct messages - both triggered by keywords you choose.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center gap-2 pb-6">
            <Button variant="outline" onClick={() => navigate("/communication/instagram/automations/new")}>
              <Plus className="h-4 w-4" />
              Comment Automation
            </Button>
            <Button variant="success" onClick={() => navigate("/communication/instagram/dm-automations/new")}>
              <Plus className="h-4 w-4" />
              DM Auto-Reply
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Type</TableHead>
                  <TableHead>Keywords</TableHead>
                  <TableHead>Matching Method</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {automations.map((automation) => (
                  <TableRow key={automation.id}>
                    <TableCell>
                      <Badge variant="secondary">{automationTypeLabel(automation)}</Badge>
                    </TableCell>
                    <TableCell className="font-medium text-foreground">
                      {automation.config.trigger_keywords.join(", ") || "—"}
                    </TableCell>
                    <TableCell>
                      <Badge>{MATCHING_METHOD_LABELS[automation.config.matching_method]}</Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={automation.is_active}
                          onCheckedChange={(checked) =>
                            setActiveMutation.mutate({ id: automation.id, isActive: checked })
                          }
                          aria-label={automation.is_active ? "Pause automation" : "Resume automation"}
                        />
                        <span className="text-xs text-muted-foreground">
                          {automation.is_active ? "Active" : "Paused"}
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-2">
                        <Button variant="outline" size="sm" onClick={() => navigate(editPathFor(automation))}>
                          <Pencil className="h-3.5 w-3.5" />
                          Edit
                        </Button>
                        <Button variant="destructive" size="sm" onClick={() => setPendingDeleteId(automation.id)}>
                          <Trash2 className="h-3.5 w-3.5" />
                          Delete
                        </Button>
                      </div>
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
        title="Delete this automation?"
        description={
          pendingAutomation
            ? `This will stop matching on "${pendingAutomation.config.trigger_keywords.join(", ")}" immediately. This can't be undone.`
            : "This can't be undone."
        }
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
