import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus, Trash2, Workflow as WorkflowIcon, X } from "lucide-react";
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
  type BadgeVariant,
} from "@fusion-flow/ui";
import { ResourceUsageBadge } from "../../components/ResourceUsageBadge";
import { useResourceLimits } from "../../lib/useResourceLimits";
import { createWorkflow, deleteWorkflow, listWorkflows } from "./api";
import { DeleteWorkflowDialog } from "./components/DeleteWorkflowDialog";
import { StarterTemplatePicker } from "./components/StarterTemplatePicker";
import type { Workflow, WorkflowStarterTemplate, WorkflowStatus } from "./types";

const statusVariant: Record<WorkflowStatus, BadgeVariant> = {
  draft: "outline",
  published: "success",
  archived: "secondary",
};

/** Which step of the "New Workflow" flow is showing — `"picker"` (choose a
 * starter template or start from scratch, Phase 6) always comes first;
 * `"name"` is the same name form this page always had, now reached either
 * way (picking "Start from scratch" or a specific template). */
type NewWorkflowStep = "closed" | "picker" | "name";

export function WorkflowsListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [newWorkflowStep, setNewWorkflowStep] = useState<NewWorkflowStep>("closed");
  const [selectedTemplate, setSelectedTemplate] = useState<WorkflowStarterTemplate | null>(null);
  const [name, setName] = useState("");
  const [workflowPendingDelete, setWorkflowPendingDelete] = useState<Workflow | null>(null);
  const { usage } = useResourceLimits();
  const { atLimit } = usage("workflows");

  const { data: workflows = [], isLoading } = useQuery({ queryKey: ["workflows"], queryFn: listWorkflows });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteWorkflow(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      setWorkflowPendingDelete(null);
    },
  });

  const createMutation = useMutation({
    mutationFn: () => createWorkflow({ name, starter_template_id: selectedTemplate?.id }),
    onSuccess: (workflow) => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      navigate(`/workflows/${workflow.id}/edit`);
    },
  });

  function closeNewWorkflowFlow() {
    setNewWorkflowStep("closed");
    setSelectedTemplate(null);
    setName("");
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
            onClick={() => setNewWorkflowStep((step) => (step === "closed" ? "picker" : "closed"))}
            disabled={atLimit}
            title={atLimit ? "You've reached your plan's limit" : undefined}
          >
            <Plus className="h-4 w-4" />
            New Workflow
          </Button>
        </div>
      </div>

      {newWorkflowStep === "picker" && (
        <StarterTemplatePicker onSelect={handleTemplateSelected} onCancel={closeNewWorkflowFlow} />
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
              <TableHead>Updated</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && workflows.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
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
