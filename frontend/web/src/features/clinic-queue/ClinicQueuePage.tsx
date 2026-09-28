import { useMemo, useState, type ReactNode } from "react";
import { DndContext, KeyboardSensor, PointerSensor, useDroppable, useSensor, useSensors, type DragEndEvent } from "@dnd-kit/core";
import { useQuery } from "@tanstack/react-query";
import { Plus, UserPlus } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle, cn } from "@fusion-flow/ui";
import { listDoctors, listVisits } from "./api";
import type { Doctor, PatientVisit } from "./types";
import { AddPatientModal } from "./components/AddPatientModal";
import { AssignDoctorModal } from "./components/AssignDoctorModal";
import { BillingDetailsModal } from "./components/BillingDetailsModal";
import { CompletePaymentModal } from "./components/CompletePaymentModal";
import { PatientCard } from "./components/PatientCard";

const DOCTOR_PREFIX = "doctor:";

/** A visit's current column id - the single source of truth both the
 * droppable columns and the drag-end handler key off, so "is this actually
 * a move" is one comparison, not duplicated logic in two places. */
function columnIdFor(visit: PatientVisit): string {
  if (visit.stage === "with_doctor" && visit.assigned_doctor_membership_id) {
    return `${DOCTOR_PREFIX}${visit.assigned_doctor_membership_id}`;
  }
  return visit.stage; // "reception" | "with_doctor" (unassigned, shouldn't happen) | "billing"
}

function Column({
  id,
  title,
  visits,
  cardAction,
}: {
  id: string;
  title: string;
  visits: PatientVisit[];
  cardAction?: (visit: PatientVisit) => ReactNode;
}) {
  const { setNodeRef, isOver } = useDroppable({ id });

  return (
    <Card className="flex w-72 shrink-0 flex-col">
      <CardHeader className="p-3">
        <CardTitle className="flex items-center justify-between text-sm">
          {title}
          <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-normal text-muted-foreground">
            {visits.length}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent
        ref={setNodeRef}
        className={cn(
          "flex min-h-[400px] flex-1 flex-col gap-2 p-3 pt-0 transition-colors",
          isOver && "bg-accent-soft",
        )}
      >
        {visits.length === 0 && <p className="py-6 text-center text-xs text-muted-foreground">No patients</p>}
        {visits.map((visit) => (
          <PatientCard key={visit.id} visit={visit} action={cardAction?.(visit)} />
        ))}
      </CardContent>
    </Card>
  );
}

/**
 * Reception → per-doctor columns → Billing. Drops don't move a card's data
 * directly (unlike `SidebarCustomizationCard`'s optimistic local-state
 * drag) - each cross-column drop only OPENS the modal collecting whatever
 * that transition legally requires; the card only actually moves once the
 * modal's mutation succeeds and invalidates the visits query, so a
 * dropped-but-cancelled card snaps back to its real column automatically
 * (no local state to reconcile).
 */
export function ClinicQueuePage() {
  const { data: visits = [], isLoading } = useQuery({
    queryKey: ["clinic-queue", "visits"],
    queryFn: () => listVisits(),
    refetchInterval: 15_000,
  });
  const { data: doctors = [] } = useQuery({ queryKey: ["clinic-queue", "doctors"], queryFn: listDoctors });

  const [addPatientOpen, setAddPatientOpen] = useState(false);
  const [assignTarget, setAssignTarget] = useState<{ visit: PatientVisit; doctorId: string } | null>(null);
  const [billingTarget, setBillingTarget] = useState<PatientVisit | null>(null);
  const [completeTarget, setCompleteTarget] = useState<PatientVisit | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 4 } }),
    useSensor(KeyboardSensor),
  );

  const visitsByColumn = useMemo(() => {
    const map = new Map<string, PatientVisit[]>();
    for (const visit of visits) {
      const columnId = columnIdFor(visit);
      const existing = map.get(columnId) ?? [];
      existing.push(visit);
      map.set(columnId, existing);
    }
    return map;
  }, [visits]);

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over) return;
    const visit = visits.find((v) => v.id === String(active.id));
    if (!visit) return;
    const targetColumn = String(over.id);
    const currentColumn = columnIdFor(visit);
    if (targetColumn === currentColumn) return;

    if (targetColumn.startsWith(DOCTOR_PREFIX)) {
      setAssignTarget({ visit, doctorId: targetColumn.slice(DOCTOR_PREFIX.length) });
      return;
    }
    if (targetColumn === "billing" && visit.stage === "with_doctor") {
      setBillingTarget(visit);
      return;
    }
    // Any other drop (e.g. onto Reception, or Billing from Reception
    // directly) isn't a valid transition - the backend requires the
    // doctor's notes/amount before billing, so there's no legal shortcut
    // from Reception straight to Billing. Silently ignored; the card
    // stays put since nothing here mutates local state.
  }

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading patient queue...</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Patient Flow</h1>
          <p className="text-sm text-muted-foreground">Reception → Doctor → Billing</p>
        </div>
        <Button onClick={() => setAddPatientOpen(true)}>
          <UserPlus className="mr-1.5 h-4 w-4" />
          Add patient
        </Button>
      </div>

      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="flex flex-1 gap-4 overflow-x-auto pb-2">
          <Column id="reception" title="Reception" visits={visitsByColumn.get("reception") ?? []} />

          {doctors.length === 0 && (
            <Card className="flex w-72 shrink-0 items-center justify-center p-6 text-center text-sm text-muted-foreground">
              No doctors set up yet. Mark a staff member as a doctor in Settings to see their column here.
            </Card>
          )}
          {doctors.map((doctor: Doctor) => (
            <Column
              key={doctor.membership_id}
              id={`${DOCTOR_PREFIX}${doctor.membership_id}`}
              title={`Dr. ${doctor.name}`}
              visits={visitsByColumn.get(`${DOCTOR_PREFIX}${doctor.membership_id}`) ?? []}
              cardAction={(visit) => (
                <Button size="sm" variant="outline" onClick={() => setBillingTarget(visit)}>
                  <Plus className="mr-1 h-3.5 w-3.5" />
                  Send to billing
                </Button>
              )}
            />
          ))}

          <Column
            id="billing"
            title="Billing"
            visits={visitsByColumn.get("billing") ?? []}
            cardAction={(visit) => (
              <Button size="sm" onClick={() => setCompleteTarget(visit)}>
                Complete
              </Button>
            )}
          />
        </div>
      </DndContext>

      <AddPatientModal open={addPatientOpen} onClose={() => setAddPatientOpen(false)} />
      <AssignDoctorModal
        visit={assignTarget?.visit ?? null}
        defaultDoctorId={assignTarget?.doctorId ?? null}
        onClose={() => setAssignTarget(null)}
      />
      <BillingDetailsModal visit={billingTarget} onClose={() => setBillingTarget(null)} />
      <CompletePaymentModal visit={completeTarget} onClose={() => setCompleteTarget(null)} />
    </div>
  );
}
