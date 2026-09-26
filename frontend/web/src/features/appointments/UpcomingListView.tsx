import { Card, CardContent, CardHeader, CardTitle } from "@fusion-flow/ui";
import { ExternalLink } from "lucide-react";
import { ModeBadge, StatusBadge } from "./AppointmentBadges";
import { formatDateHuman, toDateKey } from "./appointmentHelpers";
import type { NormalizedAppointment } from "./appointmentHelpers";

/**
 * Chronological list of every appointment whose `appointment_date` is today
 * or later. Records with no parseable `appointment_date` (pre-dating that
 * field) are un-datable and can't be sorted/shown here - they're rendered
 * in a separate "Legacy bookings" section below instead of being dropped.
 */
export function UpcomingListView({ appointments }: { appointments: NormalizedAppointment[] }) {
  const todayKey = toDateKey(new Date());

  const upcoming = appointments
    .filter((appt): appt is NormalizedAppointment & { dateKey: string } => !appt.isLegacy && appt.dateKey !== null && appt.dateKey >= todayKey)
    .sort((a, b) => {
      if (a.dateKey !== b.dateKey) return a.dateKey.localeCompare(b.dateKey);
      return (a.timeSlot ?? "").localeCompare(b.timeSlot ?? "");
    });

  const legacy = appointments.filter((appt) => appt.isLegacy);

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader>
          <CardTitle>Upcoming appointments</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          {upcoming.length === 0 && <p className="text-sm text-muted-foreground">No upcoming appointments.</p>}
          {upcoming.map((appt) => (
            <div
              key={appt.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-border p-3"
            >
              <div className="flex min-w-[10rem] flex-col gap-0.5">
                <span className="font-medium text-foreground">{appt.customerName}</span>
                <span className="text-sm text-muted-foreground">{appt.service ?? "—"}</span>
              </div>
              <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                <span>{formatDateHuman(appt.date)}</span>
                <span>{appt.timeSlot ?? "—"}</span>
                <ModeBadge mode={appt.mode} />
                {appt.mode === "online" && appt.meetLink && (
                  <a
                    href={appt.meetLink}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-accent hover:underline"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Join
                  </a>
                )}
                <StatusBadge status={appt.status} />
              </div>
            </div>
          ))}
        </CardContent>
      </Card>

      {legacy.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Legacy bookings</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-2">
            {legacy.map((appt) => (
              <div key={appt.id} className="flex flex-col gap-1 rounded-md border border-dashed border-border p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-foreground">{appt.customerName}</span>
                  <StatusBadge status={appt.status} />
                </div>
                {appt.service && <span className="text-muted-foreground">{appt.service}</span>}
                <span className="text-xs text-muted-foreground">{appt.legacyPreferredTime ?? "No date/time on record"}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
