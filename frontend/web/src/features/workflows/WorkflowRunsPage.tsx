import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import {
  Badge,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  type BadgeVariant,
} from "@fusion-flow/ui";
import { getWorkflow, getWorkflowRun, listWorkflowRuns, listWorkflowVersions } from "./api";
import type { RunStatus } from "./types";
import { RunStepTrace } from "./components/RunStepTrace";

const statusVariant: Record<RunStatus, BadgeVariant> = {
  running: "default",
  waiting: "outline",
  completed: "success",
  failed: "destructive",
  cancelled: "secondary",
};

// Only "waiting" needs a friendlier label than its raw status string - a
// paused run is otherwise indistinguishable from "running" at a glance.
const statusLabel: Partial<Record<RunStatus, string>> = {
  waiting: "Waiting for reply",
};

export function WorkflowRunsPage() {
  const { id } = useParams<{ id: string }>();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  const { data: workflow } = useQuery({
    queryKey: ["workflow", id],
    queryFn: () => getWorkflow(id as string),
    enabled: !!id,
  });
  const { data: runs = [], isLoading } = useQuery({
    queryKey: ["workflow-runs", id],
    queryFn: () => listWorkflowRuns(id as string),
    enabled: !!id,
    refetchInterval: 5000, // outbox-driven runs can complete a few seconds after the page loads
  });
  const { data: runDetail } = useQuery({
    queryKey: ["workflow-run", selectedRunId],
    queryFn: () => getWorkflowRun(selectedRunId as string),
    enabled: !!selectedRunId,
  });
  const { data: versions = [] } = useQuery({
    queryKey: ["workflow-versions", id],
    queryFn: () => listWorkflowVersions(id as string),
    enabled: !!id,
  });

  // The step trace's container-nesting indentation needs to know which
  // graph node ids are embedded inside a container - resolved from the
  // exact version this run executed (compiled_graph and .graph share the
  // same node/parentId shape; either is fine for structure lookups since
  // template resolution never changes a node's id or parentId).
  const runVersion = versions.find((v) => v.id === runDetail?.workflow_version_id);
  const nodeParentMap = new Map(
    (runVersion?.graph.nodes ?? []).map((n) => [n.id, n.parentId ?? null]),
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center gap-3">
        <Link to={id ? `/workflows/${id}/edit` : "/workflows"} className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="h-4 w-4" />
        </Link>
        <div>
          <h1 className="text-2xl font-semibold text-foreground">{workflow?.name ?? "Workflow"} — Runs</h1>
          <p className="text-sm text-muted-foreground">Every run this workflow has recorded, with a full step trace.</p>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Run history</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Started</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Trigger</TableHead>
                  <TableHead>Steps</TableHead>
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
                {!isLoading && runs.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="text-center text-muted-foreground">
                      No runs yet — publish and trigger (or simulate) this workflow to see one here.
                    </TableCell>
                  </TableRow>
                )}
                {runs.map((run) => (
                  <TableRow
                    key={run.id}
                    className="cursor-pointer"
                    data-state={selectedRunId === run.id ? "selected" : undefined}
                    onClick={() => setSelectedRunId(run.id)}
                  >
                    <TableCell className="text-muted-foreground">
                      {new Date(run.started_at).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariant[run.status]}>{statusLabel[run.status] ?? run.status}</Badge>
                    </TableCell>
                    <TableCell className="max-w-[10rem] truncate font-mono text-xs text-muted-foreground">
                      {run.trigger_event_ref ?? "-"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{run.loop_guard_count}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Step trace</CardTitle>
          </CardHeader>
          <CardContent>
            {!selectedRunId && <p className="text-sm text-muted-foreground">Select a run to see its step trace.</p>}
            {selectedRunId && !runDetail && <p className="text-sm text-muted-foreground">Loading steps...</p>}
            {runDetail && <RunStepTrace steps={runDetail.steps} nodeParentMap={nodeParentMap} />}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
