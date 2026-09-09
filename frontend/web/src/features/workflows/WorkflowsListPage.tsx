import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Plus, Workflow as WorkflowIcon, X } from "lucide-react";
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
import { createWorkflow, listWorkflows } from "./api";
import type { WorkflowStatus } from "./types";

const statusVariant: Record<WorkflowStatus, BadgeVariant> = {
  draft: "outline",
  published: "success",
  archived: "secondary",
};

export function WorkflowsListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);
  const [name, setName] = useState("");

  const { data: workflows = [], isLoading } = useQuery({ queryKey: ["workflows"], queryFn: listWorkflows });

  const createMutation = useMutation({
    mutationFn: () => createWorkflow({ name }),
    onSuccess: (workflow) => {
      queryClient.invalidateQueries({ queryKey: ["workflows"] });
      navigate(`/workflows/${workflow.id}/edit`);
    },
  });

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Workflows</h1>
          <p className="text-sm text-muted-foreground">
            Build, publish, and monitor automations across triggers, actions, and conditions.
          </p>
        </div>
        <Button onClick={() => setFormOpen((open) => !open)}>
          <Plus className="h-4 w-4" />
          New Workflow
        </Button>
      </div>

      {formOpen && (
        <Card>
          <CardHeader>
            <CardTitle>New workflow</CardTitle>
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
              <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>
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
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && workflows.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
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
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
