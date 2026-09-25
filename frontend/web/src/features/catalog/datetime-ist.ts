/**
 * Coupon/Offer active-window fields are always entered and displayed in
 * IST (India Standard Time, UTC+5:30, no DST) - this business always
 * operates in IST regardless of which timezone the admin's own browser/OS
 * happens to be set to (matches the `Asia/Kolkata` timezone already used
 * elsewhere for this tenant's business hours). Deliberately NOT using the
 * browser's ambient local timezone (`new Date(...).toISOString()`'s usual
 * behavior) - that produced wrong save times whenever the browser's system
 * clock wasn't itself set to IST, and a naive `iso.slice(0, 16)` for
 * display never converted away from UTC at all, showing raw UTC digits
 * mislabeled as if they were local time. Both bugs are fixed by doing the
 * UTC<->IST conversion explicitly here instead of relying on either one.
 */

const IST_OFFSET_MINUTES = 5 * 60 + 30;

/** A `datetime-local` input's `"YYYY-MM-DDTHH:mm"` value, entered as IST
 * wall-clock time, converted to a real UTC ISO string for the API. */
export function istLocalToUtcIso(localValue: string): string | null {
  if (!localValue) return null;
  const [datePart, timePart] = localValue.split("T");
  const [year, month, day] = datePart.split("-").map(Number);
  const [hour, minute] = (timePart ?? "00:00").split(":").map(Number);
  const utcMillis = Date.UTC(year, month - 1, day, hour, minute) - IST_OFFSET_MINUTES * 60 * 1000;
  return new Date(utcMillis).toISOString();
}

/** A UTC ISO string from the API, converted to the IST wall-clock
 * `"YYYY-MM-DDTHH:mm"` string a `datetime-local` input expects. */
export function utcIsoToIstLocal(iso: string | null): string {
  if (!iso) return "";
  const shifted = new Date(new Date(iso).getTime() + IST_OFFSET_MINUTES * 60 * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${shifted.getUTCFullYear()}-${pad(shifted.getUTCMonth() + 1)}-${pad(shifted.getUTCDate())}` +
    `T${pad(shifted.getUTCHours())}:${pad(shifted.getUTCMinutes())}`
  );
}
