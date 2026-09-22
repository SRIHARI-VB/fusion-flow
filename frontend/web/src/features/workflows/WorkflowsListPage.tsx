import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { MessageCircle, Megaphone, Plus, Sparkles, Trash2, Workflow as WorkflowIcon, X } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  cn,
  type BadgeVariant,
} from "@fusion-flow/ui";
import { ResourceUsageBadge } from "../../components/ResourceUsageBadge";
import { useResourceLimits } from "../../lib/useResourceLimits";
import { OptionPickerCard } from "../communication/wizard";
import { useConnectorInstances } from "../connectors/hooks";
import { createWorkflow, deleteWorkflow, listWorkflows } from "./api";
import { DeleteWorkflowDialog } from "./components/DeleteWorkflowDialog";
import { StarterTemplatePicker } from "./components/StarterTemplatePicker";
import type { Workflow, WorkflowPurpose, WorkflowStarterTemplate, WorkflowStatus } from "./types";

const statusVariant: Record<WorkflowStatus, BadgeVariant> = {
  draft: "outline",
  published: "success",
  archived: "secondary",
};

/** Per-channel badge colors for the workflows list (falls back to a neutral
 * gray "General" badge for `null`/an unrecognized key) - matches this
 * codebase's established WhatsApp=green/Instagram=pink convention (see
 * `nodes/cardSummaries.ts`'s `GROUP_COLORS`'s own "Talk to Customer"=emerald
 * entry for the same green), rather than inventing new colors. */
const CHANNEL_BADGE_CLASSES: Record<string, string> = {
  whatsapp: "bg-emerald-100 text-emerald-700 border-transparent",
  instagram: "bg-pink-100 text-pink-700 border-transparent",
};
const GENERAL_BADGE_CLASSES = "bg-gray-100 text-gray-600 border-transparent";

/** Which step of the "New Workflow" flow is showing — `"purpose"` (pick
 * "Automated Conversation" vs. "Broadcast Campaign") always comes first;
 * `"channel"` (pick which connected channel this workflow is for, or
 * "General" for none) comes next; `"picker"` (choose a starter template or
 * start from scratch, Phase 6) comes after that; `"name"` is the same name
 * form this page always had, now reached either way (picking "Start from
 * scratch" or a specific template). */
type NewWorkflowStep = "closed" | "purpose" | "channel" | "picker" | "name";

const PURPOSE_OPTIONS: Array<{
  purpose: WorkflowPurpose;
  label: string;
  description: string;
  icon: typeof MessageCircle;
}> = [
  {
    purpose: "automation",
    label: "Automated Conversation",
    description: "Replies to customers automatically, one conversation at a time.",
    icon: MessageCircle,
  },
  {
    purpose: "broadcast",
    label: "Broadcast Campaign",
    description: "Sends a message to many people at once, right now or on a schedule.",
    icon: Megaphone,
  },
];

export function WorkflowsListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [newWorkflowStep, setNewWorkflowStep] = useState<NewWorkflowStep>("closed");
  const [purpose, setPurpose] = useState<WorkflowPurpose>("automation");
  const [channelConnectorTypeKey, setChannelConnectorTypeKey] = useState<string | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<WorkflowStarterTemplate | null>(null);
  const [name, setName] = useState("");
  const [workflowPendingDelete, setWorkflowPendingDelete] = useState<Workflow | null>(null);
  const { usage } = useResourceLimits();
  const { atLimit } = usage("workflows");

  const { data: workflows = [], isLoading } = useQuery({ queryKey: ["workflows"], queryFn: listWorkflows });
  const { data: connectorInstances = [] } = useConnectorInstances();

  /** One entry per distinct connected connector type - dedupes multiple
   * instances of the same type (e.g. two WhatsApp numbers) down to one
   * channel choice, keyed by `connector_type_key`. */
  const channelOptions = useMemo(() => {
    const byKey = new Map<string, string>();
    for (const instance of connectorInstances) {
      if (instance.state !== "connected") continue;
      if (!byKey.has(instance.connector_type_key)) {
        byKey.set(instance.connector_type_key, instance.connector_type_display_name);
      }
    }
    return Array.from(byKey, ([key, label]) => ({ key, label }));
  }, [connectorInstances]);

  /** `connector_type_key` -> display label, for the list badge - falls back
   * to the raw key capitalized if the connector was disconnected/removed
   * since this workflow was created (same fallback `BroadcastCampaignWizardPage.tsx`
   * implicitly relies on via `connector_type_display_name` off a *currently
   * connected* instance). */
  const channelLabelByKey = useMemo(() => {
    const byKey = new Map<string, string>();
    for (const instance of connectorInstances) {
      if (!byKey.has(instance.connector_type_key)) {
        byKey.set(instance.connector_type_key, instance.connector_type_display_name);
      }
    }
    return byKey;
  }, [connectorInstances]);

  function channelLabel(key: string): string {
    return channelLabelByKey.get(key) ?? key.charAt(0).toUpperCase() + key.slice(1);
  }

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteWorkflow(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      setWorkflowPendingDelete(null);
    },
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createWorkflow({
        name,
        starter_template_id: selectedTemplate?.id,
        purpose,
        channel_connector_type_key: channelConnectorTypeKey,
      }),
    onSuccess: (workflow) => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      navigate(`/workflows/${workflow.id}/edit`);
    },
  });

  function closeNewWorkflowFlow() {
    setNewWorkflowStep("closed");
    setPurpose("automation");
    setChannelConnectorTypeKey(null);
    setSelectedTemplate(null);
    setName("");
  }

  function handlePurposeSelected(selected: WorkflowPurpose) {
    setPurpose(selected);
    setNewWorkflowStep("channel");
  }

  function handleChannelSelected(key: string | null) {
    setChannelConnectorTypeKey(key);
    setNewWorkflowStep("picker");
  }

  function handleTemplateSelected(template: WorkflowStarterTemplate | null) {
    setSelectedTemplate(template);
    setName(template ? template.name : "");
    setNewWorkflowStep("name");
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Workflows</h1>
          <p className="text-sm text-muted-foreground">
            Build, publish, and monitor automations across triggers, actions, and conditions.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <ResourceUsageBadge resourceKey="workflows" />
          <Button
            onClick={() => setNewWorkflowStep((step) => (step === "closed" ? "purpose" : "closed"))}
            disabled={atLimit}
            title={atLimit ? "You've reached your plan's limit" : undefined}
          >
            <Plus className="h-4 w-4" />
            New Workflow
          </Button>
        </div>
      </div>

      {newWorkflowStep === "purpose" && (
        <Card>
          <CardContent className="flex flex-col gap-3 py-4">
            <div>
              <p className="text-sm font-semibold text-foreground">What kind of workflow is this?</p>
              <p className="text-xs text-muted-foreground">
                This decides which triggers you'll be able to start it with — you can't mix the two in one
                workflow.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {PURPOSE_OPTIONS.map(({ purpose: optionPurpose, label, description, icon: Icon }) => (
                <button
                  key={optionPurpose}
                  type="button"
                  className={cn(
                    "flex flex-col items-start gap-2 rounded-md border border-border bg-background p-4 text-left",
                    "hover:border-accent hover:bg-accent-soft",
                  )}
                  onClick={() => handlePurposeSelected(optionPurpose)}
                >
                  <span className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-accent">
                    <Icon className="h-5 w-5" />
                  </span>
                  <span className="text-sm font-medium text-foreground">{label}</span>
                  <span className="text-xs text-muted-foreground">{description}</span>
                </button>
              ))}
            </div>

            <div className="flex justify-end border-t border-border pt-3">
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-foreground hover:underline"
                onClick={closeNewWorkflowFlow}
              >
                Cancel
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {newWorkflowStep === "channel" && (
        <Card>
          <CardContent className="flex flex-col gap-3 py-4">
            <div>
              <p className="text-sm font-semibold text-foreground">Which channel is this workflow for?</p>
              <p className="text-xs text-muted-foreground">
                Purely informational — shown as a badge on your workflows list so you can tell them apart
                at a glance. It doesn't restrict which triggers or actions you can use.
              </p>
            </div>

            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <OptionPickerCard
                title="General"
                description="Not tied to one channel — e.g. a payment- or schedule-triggered workflow."
                selected={channelConnectorTypeKey === null}
                onSelect={() => handleChannelSelected(null)}
              />
              {channelOptions.map(({ key, label }) => (
                <OptionPickerCard
                  key={key}
                  title={label}
                  description={`Workflows that talk to customers over ${label}.`}
                  selected={channelConnectorTypeKey === key}
                  onSelect={() => handleChannelSelected(key)}
                />
              ))}
            </div>

            {channelOptions.length === 0 && (
              <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Sparkles className="h-3.5 w-3.5" />
                No channels connected yet — that's fine, pick "General" for now and connect one later.
              </p>
            )}

            <div className="flex justify-end gap-4 border-t border-border pt-3">
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-foreground hover:underline"
                onClick={() => setNewWorkflowStep("purpose")}
              >
                Back
              </button>
              <button
                type="button"
                className="text-xs text-muted-foreground hover:text-foreground hover:underline"
                onClick={closeNewWorkflowFlow}
              >
                Cancel
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {newWorkflowStep === "picker" && (
        <StarterTemplatePicker
          purpose={purpose}
          onSelect={handleTemplateSelected}
          onCancel={closeNewWorkflowFlow}
          onBack={() => setNewWorkflowStep("channel")}
        />
      )}

      {newWorkflowStep === "name" && (
        <Card>
          <CardHeader>
            <CardTitle>{selectedTemplate ? `New workflow from "${selectedTemplate.name}"` : "New workflow"}</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="flex items-end gap-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (name.trim()) createMutation.mutate();
              }}
            >
              <div className="flex flex-1 flex-col gap-1.5">
                <label htmlFor="workflow-name" className="text-sm font-medium">
                  Name
                </label>
                <Input
                  id="workflow-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. New WhatsApp message triage"
                />
              </div>
              <Button type="submit" disabled={createMutation.isPending || !name.trim()}>
                {createMutation.isPending ? "Creating..." : "Create"}
              </Button>
              <Button type="button" variant="outline" onClick={() => setNewWorkflowStep("picker")}>
                Back
              </Button>
              <Button type="button" variant="outline" onClick={closeNewWorkflowFlow}>
                <X className="h-4 w-4" />
                Cancel
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Channel</TableHead>
              <TableHead>Updated</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && workflows.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No workflows yet — create one to get started.
                </TableCell>
              </TableRow>
            )}
            {workflows.map((workflow) => (
              <TableRow
                key={workflow.id}
                className="cursor-pointer"
                onClick={() => navigate(`/workflows/${workflow.id}/edit`)}
              >
                <TableCell className="font-medium text-foreground">
                  <span className="flex items-center gap-2">
                    <WorkflowIcon className="h-4 w-4 text-accent" />
                    {workflow.name}
                  </span>
                </TableCell>
                <TableCell>
                  <Badge variant={statusVariant[workflow.status]}>{workflow.status}</Badge>
                </TableCell>
                <TableCell>
                  {workflow.channel_connector_type_key ? (
                    <Badge className={CHANNEL_BADGE_CLASSES[workflow.channel_connector_type_key] ?? GENERAL_BADGE_CLASSES}>
                      {channelLabel(workflow.channel_connector_type_key)}
                    </Badge>
                  ) : (
                    <Badge className={GENERAL_BADGE_CLASSES}>General</Badge>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(workflow.updated_at).toLocaleString()}
                </TableCell>
                <TableCell>
                  <button
                    type="button"
                    aria-label={`Delete ${workflow.name}`}
                    title="Delete workflow"
                    className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
                    onClick={(event) => {
                      // Must not also trigger the row's own onClick
                      // navigation to the editor.
                      event.stopPropagation();
                      setWorkflowPendingDelete(workflow);
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {workflowPendingDelete && (
        <DeleteWorkflowDialog
          workflowName={workflowPendingDelete.name}
          isDeleting={deleteMutation.isPending}
          onCancel={() => setWorkflowPendingDelete(null)}
          onConfirm={() => deleteMutation.mutate(workflowPendingDelete.id)}
        />
      )}
    </div>
  );
}
