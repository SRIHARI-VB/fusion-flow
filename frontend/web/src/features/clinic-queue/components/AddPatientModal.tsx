import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button, Input } from "@fusion-flow/ui";
import { createPatient, listDoctors, listTodaysConfirmedAppointments } from "../api";
import { Modal } from "./Modal";

/** Reused directly from `features/orders/OrderDetailPage.tsx`'s established
 * raw-`<select>` styling convention - this app's shared UI package has no
 * `Select` component yet. */
const selectClass = "h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground";

export function AddPatientModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [appointmentRefId, setAppointmentRefId] = useState("");

  const { data: doctors = [] } = useQuery({ queryKey: ["clinic-queue", "doctors"], queryFn: listDoctors, enabled: open });
  const { data: todaysAppointments = [] } = useQuery({
    queryKey: ["clinic-queue", "todays-appointments"],
    queryFn: listTodaysConfirmedAppointments,
    enabled: open,
  });

  const mutation = useMutation({
    mutationFn: () =>
      createPatient({
        name: name.trim(),
        phone: phone.trim(),
        assigned_doctor_membership_id: doctorId || null,
        appointment_ref_id: appointmentRefId || null,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["clinic-queue", "visits"] });
      reset();
      onClose();
    },
  });

  function reset() {
    setName("");
    setPhone("");
    setDoctorId("");
    setAppointmentRefId("");
  }

  function handleClose() {
    reset();
    onClose();
  }

  function applyAppointment(id: string) {
    setAppointmentRefId(id);
    if (!id) return;
    const appointment = todaysAppointments.find((a) => a.id === id);
    if (!appointment) return;
    setName(appointment.payload.customer_name ?? "");
  }

  const canSubmit = name.trim().length > 0 && phone.trim().length > 0 && !mutation.isPending;

  return (
    <Modal open={open} title="Add patient" description="Checks the patient in at Reception." onClose={handleClose}>
      {todaysAppointments.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <label className="text-sm font-medium text-foreground">Quick check-in (today's appointments)</label>
          <select className={selectClass} value={appointmentRefId} onChange={(e) => applyAppointment(e.target.value)}>
            <option value="">Type details manually instead...</option>
            {todaysAppointments.map((appointment) => (
              <option key={appointment.id} value={appointment.id}>
                {appointment.payload.customer_name ?? "Unnamed"}
                {appointment.payload.time_slot ? ` — ${appointment.payload.time_slot}` : ""}
              </option>
            ))}
          </select>
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground">Patient name</label>
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Jane Doe" autoFocus />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground">Phone number</label>
        <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 98765 43210" />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-sm font-medium text-foreground">Assign doctor (optional)</label>
        <select className={selectClass} value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
          <option value="">Not yet — leave in Reception</option>
          {doctors.map((doctor) => (
            <option key={doctor.membership_id} value={doctor.membership_id}>
              {doctor.name}
            </option>
          ))}
        </select>
      </div>

      {mutation.isError && <p className="text-sm text-destructive">Could not add patient. Please try again.</p>}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={handleClose} disabled={mutation.isPending}>
          Cancel
        </Button>
        <Button onClick={() => mutation.mutate()} disabled={!canSubmit}>
          {mutation.isPending ? "Adding..." : "Add patient"}
        </Button>
      </div>
    </Modal>
  );
}
