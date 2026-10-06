import { ExternalLink, X } from "lucide-react";
import { ModeBadge, StatusBadge } from "./AppointmentBadges";
import { formatDateKeyHuman } from "./appointmentHelpers";
import type { NormalizedAppointment } from "./appointmentHelpers";

/**
 * Local, deliberately small overlay for a single calendar day's full
 * appointment list - `@fusion-flow/ui` has no `Dialog` component yet (see
 * `features/connectors/components/ConfirmDialog.tsx` for the same pattern
 * used elsewhere in this app), so this stays feature-scoped rather than
 * growing the shared package for one view.
 */
interface DayDetailsModalProps {
  open: boolean;
  dateKey: string | null;
  appointments: NormalizedAppointment[];
  onClose: () => void;
}

export function DayDetailsModal({ open, dateKey, appointments, onClose }: DayDetailsModalProps) {
  if (!open || !dateKey) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={formatDateKeyHuman(dateKey)}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[80vh] w-full max-w-lg flex-col rounded-lg border border-border bg-card shadow-card"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-base font-semibold text-foreground">{formatDateKeyHuman(dateKey)}</h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-5">
          {appointments.length === 0 ? (
            <p className="text-sm text-muted-foreground">No appointments on this day.</p>
          ) : (
            <ul className="flex flex-col gap-3">
              {appointments.map((appt) => (
                <li key={appt.id} className="rounded-md border border-border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-foreground">{appt.customerName}</span>
                    <StatusBadge status={appt.status} />
                  </div>
                  {appt.customerPhone && <div className="mt-1 text-sm text-muted-foreground">{appt.customerPhone}</div>}
                  <div className="mt-1 text-sm text-muted-foreground">{appt.timeSlot ?? "No time specified"}</div>
                  {appt.service && <div className="mt-1 text-sm text-foreground">{appt.service}</div>}
                  <div className="mt-2 flex flex-wrap items-center gap-3">
                    <ModeBadge mode={appt.mode} />
                    {appt.mode === "online" && appt.meetLink && (
                      <a
                        href={appt.meetLink}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
                      >
                        <ExternalLink className="h-3 w-3" />
                        Join meeting
                      </a>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
