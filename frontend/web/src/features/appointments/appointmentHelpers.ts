/**
 * Normalization + calendar-math helpers for the appointments page.
 *
 * The "appointment" business-object type's payload is a freeform bag of
 * whatever fields the tenant has defined (`ObjectRecord.payload`). This
 * module turns that into a stable `NormalizedAppointment` shape the
 * calendar/list views can render without each of them re-deriving parsing
 * and legacy-detection rules.
 */
import type { AppointmentMode, ObjectRecord } from "./types";

export interface NormalizedAppointment {
  id: string;
  /** True when the record predates `appointment_date` (or the value present
   * isn't a parseable date) - i.e. it only has the old `service` /
   * `preferred_time` / `status` fields. These can't be placed on the
   * calendar and are shown separately as "Legacy bookings". */
  isLegacy: boolean;
  customerName: string;
  service: string | null;
  timeSlot: string | null;
  mode: AppointmentMode | null;
  meetLink: string | null;
  status: string | null;
  date: Date | null;
  /** Local `YYYY-MM-DD` key for grouping onto the calendar / comparing to "today". Null for legacy records. */
  dateKey: string | null;
  /** Raw `preferred_time` free-text, kept only for legacy display. */
  legacyPreferredTime: string | null;
  createdAt: string;
}

function pad(value: number): string {
  return value < 10 ? `0${value}` : String(value);
}

function nonEmptyString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/**
 * Parses a date-typed custom field value into a local `Date` at midnight.
 * Handles both plain `YYYY-MM-DD` values and full ISO datetimes by reading
 * the date portion directly (via regex) rather than handing the whole
 * string to `new Date(...)`, which would parse a date-only string as UTC
 * midnight and can roll over to the wrong local day for tenants west of
 * UTC. Falls back to generic `Date` parsing for anything else, and returns
 * `null` (never throws) for unparseable/legacy values.
 */
export function parseAppointmentDate(value: unknown): Date | null {
  if (typeof value !== "string" || !value.trim()) return null;
  const dateOnlyMatch = value.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (dateOnlyMatch) {
    const [, y, m, d] = dateOnlyMatch;
    const date = new Date(Number(y), Number(m) - 1, Number(d));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function toDateKey(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

export function addMonths(date: Date, delta: number): Date {
  return new Date(date.getFullYear(), date.getMonth() + delta, 1);
}

export function isSameMonth(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
}

export function monthLabel(date: Date): string {
  return date.toLocaleDateString(undefined, { month: "long", year: "numeric" });
}

/** 42 (6x7) calendar cells covering the full weeks that contain `monthAnchor`'s month, Sunday-first. */
export function buildMonthGrid(monthAnchor: Date): Date[] {
  const firstOfMonth = startOfMonth(monthAnchor);
  const gridStart = new Date(firstOfMonth);
  gridStart.setDate(gridStart.getDate() - firstOfMonth.getDay());
  return Array.from({ length: 42 }, (_, i) => {
    const day = new Date(gridStart);
    day.setDate(gridStart.getDate() + i);
    return day;
  });
}

export function formatDateHuman(date: Date | null): string {
  if (!date) return "—";
  return date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

export function formatDateKeyHuman(dateKey: string): string {
  const date = parseAppointmentDate(dateKey);
  if (!date) return dateKey;
  return date.toLocaleDateString(undefined, {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/**
 * Adapts one raw `ObjectRecord` into the shape the calendar/list views
 * render. `resolveCustomerName` is only consulted when the record has no
 * `customer_name` payload value directly (i.e. legacy records) - it's the
 * existing customers-API-backed lookup from `AppointmentRecordsPage`.
 */
export function normalizeAppointment(
  record: ObjectRecord,
  resolveCustomerName: (customerId: string | null) => string,
): NormalizedAppointment {
  const payload = record.payload ?? {};

  const directCustomerName = nonEmptyString(payload.customer_name);
  const date = parseAppointmentDate(payload.appointment_date);
  const modeRaw = typeof payload.appointment_mode === "string" ? payload.appointment_mode.toLowerCase() : null;
  const mode: AppointmentMode | null = modeRaw === "online" || modeRaw === "offline" ? modeRaw : null;
  const meetLinkRaw = nonEmptyString(payload.meet_link);

  return {
    id: record.id,
    isLegacy: date === null,
    customerName: directCustomerName ?? resolveCustomerName(record.customer_id),
    service: nonEmptyString(payload.service),
    timeSlot: nonEmptyString(payload.time_slot),
    mode,
    meetLink: mode === "online" ? meetLinkRaw : null,
    status: nonEmptyString(payload.status),
    date,
    dateKey: date ? toDateKey(date) : null,
    legacyPreferredTime: nonEmptyString(payload.preferred_time),
    createdAt: record.created_at,
  };
}
