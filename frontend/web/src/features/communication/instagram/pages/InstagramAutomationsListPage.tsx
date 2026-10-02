import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  AtSign,
  ChevronDown,
  Heart,
  Instagram,
  LayoutGrid,
  Link2,
  MessageCircle,
  MessageSquare,
  Pencil,
  Plus,
  Settings,
  ShieldAlert,
  Ticket,
  Trash2,
  UserCog,
} from "lucide-react";
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
  DropdownMenuLabel,
  DropdownMenuSeparator,
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
import { fetchTriggerOverlaps } from "../../../workflows/api";
import { useDeleteInstagramAutomation, useInstagramAutomations, useSetInstagramAutomationActive } from "../hooks";
import { MATCHING_METHOD_LABELS } from "../constants";
import type { InstagramMatchingMethod, PredefinedAutomation } from "../types";

/** Every Instagram automation type this list page knows how to display and
 * link to, keyed by the backend's `automation_type` string. Each new
 * automation type built against this feature (see the sibling wizard
 * pages) only needs one entry added here - the rest of this file is
 * generic across all of them. `automation.config`'s real shape differs
 * per type (the shared `PredefinedAutomation.config` union in `types.ts`
 * only covers the two oldest types), so `summary`/`matchingMethod` below
 * read it as `Record<string, unknown>` rather than fighting a stricter
 * type per row. */
interface AutomationTypeMeta {
  label: string;
  icon: typeof MessageSquare;
  newPath: string;
  editPath: (id: string) => string;
  summary: (config: Record<string, unknown>) => string;
  matchingMethod: (config: Record<string, unknown>) => string | null;
}

function keywordSummary(config: Record<string, unknown>): string {
  const keywords = config.trigger_keywords;
  return Array.isArray(keywords) && keywords.length > 0 ? keywords.join(", ") : "—";
}

function matchingMethodLabel(config: Record<string, unknown>): string | null {
  const method = config.matching_method as InstagramMatchingMethod | undefined;
  return method ? MATCHING_METHOD_LABELS[method] : null;
}

const AUTOMATION_TYPE_META: Record<string, AutomationTypeMeta> = {
  "instagram.comment_automation": {
    label: "Comment Automation",
    icon: MessageSquare,
    newPath: "/communication/instagram/automations/new",
    editPath: (id) => `/communication/instagram/automations/${id}/edit`,
    summary: keywordSummary,
    matchingMethod: matchingMethodLabel,
  },
  "instagram.dm_automation": {
    label: "DM Auto-Reply",
    icon: MessageCircle,
    newPath: "/communication/instagram/dm-automations/new",
    editPath: (id) => `/communication/instagram/dm-automations/${id}/edit`,
    summary: keywordSummary,
    matchingMethod: matchingMethodLabel,
  },
  "instagram.mention_automation": {
    label: "Mention Auto-Reply",
    icon: AtSign,
    newPath: "/communication/instagram/mention-automations/new",
    editPath: (id) => `/communication/instagram/mention-automations/${id}/edit`,
    summary: keywordSummary,
    matchingMethod: matchingMethodLabel,
  },
  "instagram.comment_moderation": {
    label: "Comment Moderation",
    icon: ShieldAlert,
    newPath: "/communication/instagram/moderation-automations/new",
    editPath: (id) => `/communication/instagram/moderation-automations/${id}/edit`,
    summary: keywordSummary,
    matchingMethod: matchingMethodLabel,
  },
  "instagram.story_reply_automation": {
    label: "Story Reply Auto-Reply",
    icon: Instagram,
    newPath: "/communication/instagram/story-reply-automations/new",
    editPath: (id) => `/communication/instagram/story-reply-automations/${id}/edit`,
    summary: keywordSummary,
    matchingMethod: matchingMethodLabel,
  },
  "instagram.button_menu_automation": {
    label: "Button Menu",
    icon: LayoutGrid,
    newPath: "/communication/instagram/button-menu-automations/new",
    editPath: (id) => `/communication/instagram/button-menu-automations/${id}/edit`,
    summary: keywordSummary,
    matchingMethod: matchingMethodLabel,
  },
  "instagram.referral_automation": {
    label: "Ad/Link Campaign Router",
    icon: Link2,
    newPath: "/communication/instagram/referral-automations/new",
    editPath: (id) => `/communication/instagram/referral-automations/${id}/edit`,
    summary: (config) => {
      const rules = config.rules;
      const count = Array.isArray(rules) ? rules.length : 0;
      return count === 1 ? "1 rule" : `${count} rules`;
    },
    matchingMethod: () => null,
  },
  "instagram.reaction_automation": {
    label: "Reaction Follow-Up",
    icon: Heart,
    newPath: "/communication/instagram/reaction-automations/new",
    editPath: (id) => `/communication/instagram/reaction-automations/${id}/edit`,
    summary: (config) => {
      const reaction = config.reaction_type;
      return typeof reaction === "string" ? `Reaction: ${reaction}` : "—";
    },
    matchingMethod: () => null,
  },
  "instagram.handoff_automation": {
    label: "Human Handoff",
    icon: UserCog,
    newPath: "/communication/instagram/handoff-automations/new",
    editPath: (id) => `/communication/instagram/handoff-automations/${id}/edit`,
    summary: keywordSummary,
    matchingMethod: matchingMethodLabel,
  },
  "instagram.comment_menu_automation": {
    label: "Comment-to-DM Menu",
    icon: Ticket,
    newPath: "/communication/instagram/comment-menu-automations/new",
    editPath: (id) => `/communication/instagram/comment-menu-automations/${id}/edit`,
    summary: keywordSummary,
    matchingMethod: matchingMethodLabel,
  },
};

const NEW_AUTOMATION_GROUPS: { label: string; types: string[] }[] = [
  {
    label: "Reply & Engage",
    types: [
      "instagram.comment_automation",
      "instagram.dm_automation",
      "instagram.mention_automation",
      "instagram.story_reply_automation",
    ],
  },
  { label: "Moderate", types: ["instagram.comment_moderation"] },
  {
    label: "Marketing & Menus",
    types: [
      "instagram.button_menu_automation",
      "instagram.referral_automation",
      "instagram.reaction_automation",
      "instagram.comment_menu_automation",
    ],
  },
  { label: "Support", types: ["instagram.handoff_automation"] },
];

function metaFor(automation: PredefinedAutomation): AutomationTypeMeta {
  return (
    AUTOMATION_TYPE_META[automation.automation_type] ?? {
      label: automation.automation_type,
      icon: MessageSquare,
      newPath: "/communication/instagram/automations",
      editPath: () => "/communication/instagram/automations",
      summary: () => "—",
      matchingMethod: () => null,
    }
  );
}

/**
 * `/communication/instagram/automations` - list of every predefined
 * automation configured against the tenant's connected Instagram account,
 * across every registered Instagram automation type (see
 * `AUTOMATION_TYPE_META` above). There is no `name` field on the
 * backend's `PredefinedAutomation` DTO, so each type's own summary
 * (usually trigger keywords) stands in as the row's label.
 */
export function InstagramAutomationsListPage() {
  const navigate = useNavigate();
  const { data: automations, isLoading } = useInstagramAutomations();
  const setActiveMutation = useSetInstagramAutomationActive();
  const deleteMutation = useDeleteInstagramAutomation();
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  // Collision warning: 2+ published workflows both reacting to the same
  // kind of Instagram event (comments, DMs, button taps). Meta allows
  // only one Private Reply per comment, so when this overlaps, whichever
  // workflow's reply reaches Meta first "wins" and the other's gets
  // silently rejected - see the backend's `get_trigger_overlaps` docstring.
  const { data: triggerOverlaps } = useQuery({
    queryKey: ["workflow-trigger-overlaps"],
    queryFn: fetchTriggerOverlaps,
  });
  const instagramOverlaps = (triggerOverlaps ?? []).filter((overlap) => overlap.trigger_type.startsWith("instagram."));

  const pendingAutomation = automations?.find((automation) => automation.id === pendingDeleteId);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Instagram Automations</h1>
          <p className="text-sm text-muted-foreground">
            Automatically reply, moderate, and route conversations on this Instagram account.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => navigate("/communication/instagram/ice-breakers")}>
            <Settings className="h-4 w-4" />
            Welcome Menu
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger>
              <Button variant="success">
                <Plus className="h-4 w-4" />
                New Automation
                <ChevronDown className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              {NEW_AUTOMATION_GROUPS.map((group, groupIndex) => (
                <div key={group.label}>
                  {groupIndex > 0 && <DropdownMenuSeparator />}
                  <DropdownMenuLabel>{group.label}</DropdownMenuLabel>
                  {group.types.map((type) => {
                    const meta = AUTOMATION_TYPE_META[type];
                    const Icon = meta.icon;
                    return (
                      <DropdownMenuItem key={type} onClick={() => navigate(meta.newPath)}>
                        <Icon className="h-3.5 w-3.5" />
                        {meta.label}
                      </DropdownMenuItem>
                    );
                  })}
                </div>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {instagramOverlaps.length > 0 && (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="flex items-start gap-3 pt-6">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium text-foreground">
                Multiple automations react to the same event here
              </p>
              {instagramOverlaps.map((overlap) => (
                <p key={`${overlap.trigger_type}-${overlap.connector_instance_id ?? "any"}`} className="text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{overlap.workflow_names.join(", ")}</span> all react
                  to{" "}
                  {overlap.trigger_type === "instagram.comment_received"
                    ? "comments"
                    : overlap.trigger_type === "instagram.message_received"
                      ? "direct messages"
                      : overlap.trigger_type === "instagram.postback_received"
                        ? "button taps"
                        : overlap.trigger_type}
                  . If their triggers overlap, only one reply may get through - Meta allows just one Private Reply
                  per comment, and a similar single-message window for DMs.
                </p>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

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
              Reply to comments and DMs, moderate spam, route ad traffic, or hand off to a human - all triggered by
              keywords or events you choose. Use "New Automation" above to get started.
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
                  <TableHead>Trigger</TableHead>
                  <TableHead>Matching Method</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {automations.map((automation) => {
                  const meta = metaFor(automation);
                  const config = automation.config as unknown as Record<string, unknown>;
                  const matchingMethod = meta.matchingMethod(config);
                  return (
                    <TableRow key={automation.id}>
                      <TableCell>
                        <Badge variant="secondary">{meta.label}</Badge>
                      </TableCell>
                      <TableCell className="font-medium text-foreground">{meta.summary(config)}</TableCell>
                      <TableCell>{matchingMethod ? <Badge>{matchingMethod}</Badge> : "—"}</TableCell>
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
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => navigate(meta.editPath(automation.id))}
                          >
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
                  );
                })}
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
            ? `This will stop "${metaFor(pendingAutomation).label}" (${metaFor(pendingAutomation).summary(pendingAutomation.config as unknown as Record<string, unknown>)}) immediately. This can't be undone.`
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
