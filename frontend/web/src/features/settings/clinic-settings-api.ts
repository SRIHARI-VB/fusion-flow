import { apiClient } from "../../lib/api-client";

/** Tenant-scoped custom object type key (see `business_objects` module) —
 * one record per tenant, created out-of-band today (not from this app).
 * Field keys below must exactly match that type's seeded field
 * definitions: the backend validates `ObjectRecord.payload` against them
 * with `extra="forbid"` (see `custom_fields/validation.py`), so an unknown
 * or missing-required key is rejected as a 422, not silently dropped. */
const OBJECT_TYPE_KEY = "business_settings";

export interface ClinicSettingsPayload {
  business_name: string;
  phone: string;
  address: string;
  open_time: string;
  close_time: string;
  /** weekday keys, e.g. "monday".."sunday" — fully closed days. */
  closed_weekdays: string[];
  morning_start: string;
  morning_end: string;
  afternoon_start: string;
  afternoon_end: string;
  evening_start: string;
  evening_end: string;
  /** "HH:MM" or "" — optional daily break/lunch window. */
  break_start: string;
  break_end: string;
  /** weekday keys that get auto-confirmed calendar booking instead of a
   * staff-reviewed ticket. */
  direct_booking_weekdays: string[];
  /** comma-separated "YYYY-MM-DD" one-off dates, in addition to the
   * weekday rule above. */
  direct_booking_specific_dates: string;
  /** Minutes per bookable calendar slot on a direct-booking day (10-120,
   * default 30) - how many time options the customer sees per period. */
  appointment_slot_minutes: number;
}

/** `GET /api/v1/business-objects/records/{id}` response shape. */
export interface ClinicSettingsRecord {
  id: string;
  object_type_id: string;
  payload: ClinicSettingsPayload;
  customer_id: string | null;
  created_by_run_id: string | null;
  created_at: string;
  updated_at: string;
}

/** `GET /api/v1/business-objects/types/{key}/records` — records are
 * addressed by the object type's `key` (not its id), the same identifier a
 * workflow node's `config.module` carries. `business_settings` is seeded
 * with exactly one record per tenant, so the first (and only) result is
 * this tenant's record; `null` if the type/record doesn't exist yet for
 * this tenant. */
export async function fetchClinicSettingsRecord(): Promise<ClinicSettingsRecord | null> {
  const { data } = await apiClient.get<ClinicSettingsRecord[]>(
    `/api/v1/business-objects/types/${OBJECT_TYPE_KEY}/records`,
  );
  return data[0] ?? null;
}

/** `POST /api/v1/business-objects/types/{key}/records` — only hit if a
 * tenant somehow has no record yet (the expected case, seeded already, is
 * `updateClinicSettingsRecord`). */
export async function createClinicSettingsRecord(
  payload: ClinicSettingsPayload,
): Promise<ClinicSettingsRecord> {
  const { data } = await apiClient.post<ClinicSettingsRecord>(
    `/api/v1/business-objects/types/${OBJECT_TYPE_KEY}/records`,
    { payload },
  );
  return data;
}

/** `PATCH /api/v1/business-objects/records/{record_id}` — the backend
 * merges `payload` into the record's existing payload rather than
 * replacing it (see `business_objects/service.py::update_record`), but
 * this card always submits every field from its form, so the merge is
 * effectively a full replace here. */
export async function updateClinicSettingsRecord(
  recordId: string,
  payload: ClinicSettingsPayload,
): Promise<ClinicSettingsRecord> {
  const { data } = await apiClient.patch<ClinicSettingsRecord>(
    `/api/v1/business-objects/records/${recordId}`,
    { payload },
  );
  return data;
}
