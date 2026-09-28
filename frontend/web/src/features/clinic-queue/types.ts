/** Mirrors `fusionflow.modules.clinic_queue.schemas` on the backend. */
export type PatientVisitStage = "reception" | "with_doctor" | "billing" | "completed";
export type PaymentMode = "cash" | "card" | "upi" | "insurance" | "other";

export interface PatientVisit {
  id: string;
  customer_id: string;
  customer_name: string;
  customer_phone: string | null;
  appointment_ref_id: string | null;
  assigned_doctor_membership_id: string | null;
  assigned_doctor_name: string | null;
  stage: PatientVisitStage;
  checked_in_at: string;
  doctor_started_at: string | null;
  /** Absent entirely (not null) on `/history` responses for a non-doctor
   * requester - real backend enforcement, not a UI-only hide. Treat a
   * missing key the same as `undefined`, never assume it's always present. */
  consultation_notes?: string | null;
  amount_to_collect: number | null;
  billing_started_at: string | null;
  payment_mode: PaymentMode | null;
  amount_collected: number | null;
  completed_at: string | null;
  position: number;
  created_at: string;
  updated_at: string;
}

export interface CreatePatientInput {
  name: string;
  phone: string;
  assigned_doctor_membership_id?: string | null;
  appointment_ref_id?: string | null;
}

export interface Doctor {
  membership_id: string;
  name: string;
  email: string;
}

export type StageTransitionInput =
  | { stage: "with_doctor"; assigned_doctor_membership_id: string }
  | { stage: "billing"; consultation_notes: string; amount_to_collect: number }
  | { stage: "completed"; payment_mode: PaymentMode; amount_collected?: number };

export const PAYMENT_MODE_LABELS: Record<PaymentMode, string> = {
  cash: "Cash",
  card: "Card",
  upi: "UPI",
  insurance: "Insurance",
  other: "Other",
};

/** Query params for `GET /clinic-queue/history` (History page filters). */
export interface HistoryFilters {
  date_from?: string;
  date_to?: string;
  doctor_membership_id?: string;
  payment_mode?: PaymentMode;
}

/** A subset of the `appointment` business-object type's payload, used only
 * for the "check in an existing appointment" shortcut - see
 * `features/appointments/types.ts` for the full shape this app already has
 * elsewhere; kept local/minimal here since only these fields matter for
 * pre-filling the Add Patient form. */
export interface AppointmentRecordSummary {
  id: string;
  customer_id: string | null;
  payload: {
    customer_name?: string;
    appointment_date?: string;
    status?: string;
    service?: string;
    time_slot?: string;
  };
}
