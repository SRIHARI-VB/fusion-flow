import { useState } from "react";
import { CheckCircle2, ChevronDown, ChevronRight, CircleDashed, Loader2, SkipForward, XCircle } from "lucide-react";
import { Badge, type BadgeVariant } from "@fusion-flow/ui";
import type { RunStep, StepStatus } from "../types";

/** Timeline of `WorkflowRunStep`s for one run — used by both the
 * simulate dry-run result and the `/workflows/:id/runs` step trace
 * viewer. */

const STATUS_ICON: Record<StepStatus, typeof CheckCircle2> = {
  succeeded: CheckCircle2,
  failed: XCircle,
  running: Loader2,
  pending: CircleDashed,
  skipped: SkipForward,
};

const STATUS_VARIANT: Record<StepStatus, BadgeVariant> = {
  succeeded: "success",
  failed: "destructive",
  running: "default",
  pending: "outline",
  skipped: "secondary",
};

function StepRow({ step }: { step: RunStep }) {
  const [open, setOpen] = useState(false);
  const Icon = STATUS_ICON[step.status];

  return (
    <li className="relative pl-6">
      <span className="absolute left-0 top-1 flex h-4 w-4 items-center justify-center">
        <Icon className={`h-4 w-4 ${step.status === "running" ? "animate-spin text-accent" : "text-muted-foreground"}`} />
      </span>

      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 rounded-md py-1 text-left hover:bg-muted"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="flex items-center gap-2 text-sm">
          <span className="font-mono text-xs text-muted-foreground">{step.node_id}</span>
          <span className="text-foreground">{step.node_type}</span>
        </span>
        <span className="flex items-center gap-2">
          <Badge variant={STATUS_VARIANT[step.status]}>{step.status}</Badge>
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </span>
      </button>

      {open && (
        <div className="mb-2 flex flex-col gap-2 rounded-md border border-border bg-background p-2 text-xs">
          {step.error && <p className="text-destructive">{step.error}</p>}
          <div>
            <p className="mb-1 font-medium text-muted-foreground">Input</p>
            <pre className="overflow-x-auto rounded bg-muted p-2">{JSON.stringify(step.input, null, 2)}</pre>
          </div>
          <div>
            <p className="mb-1 font-medium text-muted-foreground">Output</p>
            <pre className="overflow-x-auto rounded bg-muted p-2">{JSON.stringify(step.output, null, 2)}</pre>
          </div>
          <p className="text-muted-foreground">
            attempt {step.attempt}
            {step.started_at && ` · started ${new Date(step.started_at).toLocaleTimeString()}`}
            {step.completed_at && ` · completed ${new Date(step.completed_at).toLocaleTimeString()}`}
          </p>
        </div>
      )}
    </li>
  );
}

export function RunStepTrace({ steps }: { steps: RunStep[] }) {
  if (steps.length === 0) {
    return <p className="text-sm text-muted-foreground">No steps recorded for this run.</p>;
  }

  return (
    <ul className="flex flex-col gap-1 border-l border-border pl-2">
      {steps.map((step) => (
        <StepRow key={step.id} step={step} />
      ))}
    </ul>
  );
}
