import { apiClient } from "../../lib/api-client";
import { toDateKey } from "../appointments/appointmentHelpers";
import type {
  AppointmentRecordSummary,
  CreatePatientInput,
  Doctor,
  HistoryFilters,
  PatientVisit,
  PatientVisitStage,
  StageTransitionInput,
} from "./types";

const BASE = "/api/v1/clinic-queue";

export async function listVisits(
  stages: PatientVisitStage[] = ["reception", "with_doctor", "billing"],
): Promise<PatientVisit[]> {
  const { data } = await apiClient.get<PatientVisit[]>(`${BASE}/visits`, {
    params: { stage: stages.join(",") },
  });
  return data;
}

export async function createPatient(payload: CreatePatientInput): Promise<PatientVisit> {
  const { data } = await apiClient.post<PatientVisit>(`${BASE}/patients`, payload);
  return data;
}

export async function transitionStage(id: string, payload: StageTransitionInput): Promise<PatientVisit> {
  const { data } = await apiClient.patch<PatientVisit>(`${BASE}/visits/${id}/stage`, payload);
  return data;
}

export async function listDoctors(): Promise<Doctor[]> {
  const { data } = await apiClient.get<Doctor[]>(`${BASE}/doctors`);
  return data;
}

/** The `business_objects` list endpoint (`GET /types/{key}/records`) has no
 * query-param filtering at all - fetches every `appointment` record and
 * filters client-side to "confirmed, dated today" for the Add Patient
 * modal's quick-check-in shortcut. `toDateKey` (not a raw
 * `toISOString().slice(0,10)`) is required here - this app already fixed a
 * real timezone bug from comparing a local calendar date against a
 * UTC-derived key once this session, in `appointmentHelpers.ts`. */
export async function listTodaysConfirmedAppointments(): Promise<AppointmentRecordSummary[]> {
  const { data } = await apiClient.get<AppointmentRecordSummary[]>(
    "/api/v1/business-objects/types/appointment/records",
  );
  const todayKey = toDateKey(new Date());
  return data.filter((record) => record.payload.status === "confirmed" && record.payload.appointment_date === todayKey);
}

/** `consultation_notes` is present on every returned visit, or absent from
 * every one, depending on whether the requesting user is a doctor - never
 * a per-row difference. See `PatientVisit.consultation_notes`'s own doc. */
export async function listHistory(filters: HistoryFilters): Promise<PatientVisit[]> {
  const params: Record<string, string> = {};
  if (filters.date_from) params.date_from = filters.date_from;
  if (filters.date_to) params.date_to = filters.date_to;
  if (filters.doctor_membership_id) params.doctor_membership_id = filters.doctor_membership_id;
  if (filters.payment_mode) params.payment_mode = filters.payment_mode;
  const { data } = await apiClient.get<PatientVisit[]>(`${BASE}/history`, { params });
  return data;
}
