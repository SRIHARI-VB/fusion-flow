import { useMemo, useState } from "react";
import { Button, cn } from "@fusion-flow/ui";
import { ChevronLeft, ChevronRight } from "lucide-react";
import {
  addMonths,
  buildMonthGrid,
  isSameMonth,
  monthLabel,
  startOfMonth,
  toDateKey,
} from "./appointmentHelpers";
import type { NormalizedAppointment } from "./appointmentHelpers";
import { DayDetailsModal } from "./DayDetailsModal";

const WEEKDAY_LABELS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MAX_CHIPS_PER_DAY = 3;

/** Month-grid calendar of appointments, grouped onto `appointment_date` cells. Pending (undated) requests never appear here - see `UpcomingListView`'s "Pending requests" section. */
export function CalendarView({ appointments }: { appointments: NormalizedAppointment[] }) {
  const [monthAnchor, setMonthAnchor] = useState(() => startOfMonth(new Date()));
  const [selectedDateKey, setSelectedDateKey] = useState<string | null>(null);

  const byDate = useMemo(() => {
    const map = new Map<string, NormalizedAppointment[]>();
    for (const appt of appointments) {
      if (appt.isPending || !appt.dateKey) continue;
      const existing = map.get(appt.dateKey);
      if (existing) existing.push(appt);
      else map.set(appt.dateKey, [appt]);
    }
    for (const list of map.values()) {
      list.sort((a, b) => (a.timeSlot ?? "").localeCompare(b.timeSlot ?? ""));
    }
    return map;
  }, [appointments]);

  const days = useMemo(() => buildMonthGrid(monthAnchor), [monthAnchor]);
  const todayKey = toDateKey(new Date());
  const selectedAppointments = selectedDateKey ? byDate.get(selectedDateKey) ?? [] : [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-lg border border-border bg-card px-4 py-3">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => setMonthAnchor((current) => addMonths(current, -1))}
          aria-label="Previous month"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-foreground">{monthLabel(monthAnchor)}</span>
          <Button type="button" variant="outline" size="sm" onClick={() => setMonthAnchor(startOfMonth(new Date()))}>
            Today
          </Button>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={() => setMonthAnchor((current) => addMonths(current, 1))}
          aria-label="Next month"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <div className="grid grid-cols-7 border-b border-border bg-muted/40 text-xs font-medium text-muted-foreground">
          {WEEKDAY_LABELS.map((label) => (
            <div key={label} className="px-2 py-2 text-center">
              {label}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {days.map((day) => {
            const dateKey = toDateKey(day);
            const dayAppointments = byDate.get(dateKey) ?? [];
            const inMonth = isSameMonth(day, monthAnchor);
            const isToday = dateKey === todayKey;
            const hasAppointments = dayAppointments.length > 0;

            return (
              <div
                key={dateKey}
                onClick={() => hasAppointments && setSelectedDateKey(dateKey)}
                className={cn(
                  "min-h-[6rem] border-b border-r border-border p-1.5 text-xs [&:nth-child(7n)]:border-r-0",
                  !inMonth && "bg-muted/20 text-muted-foreground/50",
                  hasAppointments && "cursor-pointer hover:bg-muted/40",
                )}
              >
                <div
                  className={cn(
                    "mb-1 inline-flex h-5 w-5 items-center justify-center rounded-full text-[11px]",
                    isToday && "bg-accent font-semibold text-accent-foreground",
                  )}
                >
                  {day.getDate()}
                </div>
                <div className="flex flex-col gap-1">
                  {dayAppointments.slice(0, MAX_CHIPS_PER_DAY).map((appt) => (
                    <button
                      key={appt.id}
                      type="button"
                      title={[appt.customerName, appt.timeSlot, appt.service].filter(Boolean).join(" · ")}
                      onClick={(event) => {
                        event.stopPropagation();
                        setSelectedDateKey(dateKey);
                      }}
                      className="truncate rounded bg-accent-soft px-1.5 py-0.5 text-left text-[11px] text-accent hover:opacity-80"
                    >
                      {appt.customerName}
                      {appt.timeSlot ? ` · ${appt.timeSlot}` : ""}
                    </button>
                  ))}
                  {dayAppointments.length > MAX_CHIPS_PER_DAY && (
                    <span className="px-1.5 text-[11px] text-muted-foreground">
                      +{dayAppointments.length - MAX_CHIPS_PER_DAY} more
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <DayDetailsModal
        open={selectedDateKey !== null}
        dateKey={selectedDateKey}
        appointments={selectedAppointments}
        onClose={() => setSelectedDateKey(null)}
      />
    </div>
  );
}
