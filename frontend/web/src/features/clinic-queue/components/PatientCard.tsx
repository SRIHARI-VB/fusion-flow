import type { ReactNode } from "react";
import { useDraggable } from "@dnd-kit/core";
import { Badge, cn } from "@fusion-flow/ui";
import { Phone } from "lucide-react";
import type { PatientVisit } from "../types";

function timeOnly(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/**
 * A plain draggable (not `useSortable`) - within-column ordering isn't a
 * requirement here (the backend's `position` field exists but reordering
 * is explicitly low-priority per the build contract), only cross-column
 * moves matter, so the simpler `@dnd-kit/core` primitive is enough; no
 * `SortableContext` needed.
 */
export function PatientCard({ visit, action }: { visit: PatientVisit; action?: ReactNode }) {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: visit.id,
  });

  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn(
        "flex cursor-grab touch-none flex-col gap-2 rounded-md border border-border bg-card p-3 shadow-card active:cursor-grabbing",
        isDragging && "opacity-50",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="text-sm font-medium text-foreground">{visit.customer_name}</span>
        {visit.stage === "reception" && <Badge variant="secondary">Waiting</Badge>}
        {visit.stage === "with_doctor" && <Badge variant="default">With doctor</Badge>}
        {visit.stage === "billing" && <Badge variant="success">Billing</Badge>}
      </div>
      {visit.customer_phone && (
        <span className="flex items-center gap-1 text-xs text-muted-foreground">
          <Phone className="h-3 w-3" />
          {visit.customer_phone}
        </span>
      )}
      <span className="text-xs text-muted-foreground">Checked in {timeOnly(visit.checked_in_at)}</span>
      {visit.assigned_doctor_name && (
        <span className="text-xs text-muted-foreground">Dr. {visit.assigned_doctor_name}</span>
      )}
      {visit.stage === "billing" && visit.amount_to_collect != null && (
        <span className="text-xs font-medium text-foreground">Collect ₹{visit.amount_to_collect}</span>
      )}
      {action}
    </div>
  );
}
