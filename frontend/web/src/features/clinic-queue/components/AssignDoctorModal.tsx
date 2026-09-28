import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@fusion-flow/ui";
import { listDoctors, transitionStage } from "../api";
import type { PatientVisit } from "../types";
import { Modal } from "./Modal";

const selectClass = "h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground";

/**
 * Opened when a card is dropped onto a doctor column - pre-filled with
 * that doctor but still changeable (and still requires an explicit
 * confirm), so an accidental drop onto the wrong lane is trivially
 * recoverable rather than silently reassigning the patient.
 */
export function AssignDoctorModal({
  visit,
  defaultDoctorId,
  onClose,
}: {
  visit: PatientVisit | null;
  defaultDoctorId: string | null;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [doctorId, setDoctorId] = useState(defaultDoctorId ?? "");

  useEffect(() => {
    setDoctorId(defaultDoctorId ?? "");
  }, [defaultDoctorId, visit?.id]);

  const { data: doctors = [] } = useQuery({
    queryKey: ["clinic-queue", "doctors"],
    queryFn: listDoctors,
    enabled: visit !== null,
  });

  const mutation = useMutation({
    mutationFn: () => transitionStage(visit!.id, { stage: "with_doctor", assigned_doctor_membership_id: doctorId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clinic-queue", "visits"] });
      onClose();
    },
  });

  return (
    <Modal
      open={visit !== null}
      title={`Send ${visit?.customer_name ?? ""} to a doctor`}
      onClose={onClose}
    >
      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground">Doctor</label>
        <select className={selectClass} value={doctorId} onChange={(e) => setDoctorId(e.target.value)} autoFocus>
          <option value="" disabled>
            Choose a doctor...
          </option>
          {doctors.map((doctor) => (
            <option key={doctor.membership_id} value={doctor.membership_id}>
              {doctor.name}
            </option>
          ))}
        </select>
      </div>

      {mutation.isError && <p className="text-sm text-destructive">Could not assign doctor. Please try again.</p>}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>
          Cancel
        </Button>
        <Button onClick={() => mutation.mutate()} disabled={!doctorId || mutation.isPending}>
          {mutation.isPending ? "Assigning..." : "Assign"}
        </Button>
      </div>
    </Modal>
  );
}
