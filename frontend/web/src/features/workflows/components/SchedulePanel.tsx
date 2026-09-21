import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Play, Trash2, X } from "lucide-react";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Input, cn } from "@fusion-flow/ui";
import {
  createSchedule,
  deleteSchedule,
  listModules,
  listSchedules,
  updateSchedule,
  type ScheduleFrequency,
  type WorkflowSchedule,
  type WorkflowSchedulePayload,
} from "../api";
import {
  DEFAULT_STATIC_RECIPIENT_SOURCE,
  RecipientSourceField,
  type RecipientSource,
} from "./RecipientSourceField";

/**
 * Schedule editor for a "Broadcast"-purpose workflow's recurring/scheduled
 * bulk send (`WorkflowSchedule` CRUD, backend landing in parallel - see
 * `api.ts`'s own docstring for the field-name caveat). Toggled from
 * `WorkflowEditorPage.tsx`'s toolbar, same floating-panel chrome
 * (`Card`-based, absolute-positioned, a "Close" button in the header) as
 * `ValidationPanel.tsx`. No raw cron syntax is ever shown - just plain
 * frequency/time/day controls that map onto the backend's own friendly
 * schedule fields.
 */

interface SchedulePanelProps {
  workflowId: string;
  onClose: () => void;
}

// A short, common-enough hardcoded list rather than
// `Intl.supportedValuesOf?.("timeZone")` (not reliably available across
// this app's target browsers) - "UTC" first and selected by default, same
// spirit as the backend's own `timezone: "UTC"` default.
const TIMEZONES = [
  "UTC",
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Sao_Paulo",
  "Europe/London",
  "Europe/Paris",
  "Europe/Berlin",
  "Africa/Lagos",
  "Africa/Johannesburg",
  "Asia/Kolkata",
  "Asia/Dubai",
  "Asia/Singapore",
  "Asia/Tokyo",
  "Australia/Sydney",
];

const WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const segmentBase =
  "flex-1 rounded-md border px-2 py-1.5 text-xs font-medium text-center transition-colors";
const segmentInactive = "border-border bg-background text-muted-foreground hover:border-accent";
const segmentActive = "border-accent bg-accent-soft text-foreground";

interface FormState {
  frequency: ScheduleFrequency;
  run_at: string;
  time_of_day: string;
  weekdays: number[];
  day_of_month: number;
  timezone: string;
  recipient_source: RecipientSource;
}

const EMPTY_FORM: FormState = {
  frequency: "once",
  run_at: "",
  time_of_day: "09:00",
  weekdays: [],
  day_of_month: 1,
  timezone: "UTC",
  recipient_source: DEFAULT_STATIC_RECIPIENT_SOURCE,
};

function scheduleToForm(schedule: WorkflowSchedule): FormState {
  return {
    frequency: schedule.frequency,
    run_at: schedule.run_at ?? "",
    time_of_day: schedule.time_of_day ?? "09:00",
    weekdays: schedule.weekdays ?? [],
    day_of_month: schedule.day_of_month ?? 1,
    timezone: schedule.timezone,
    recipient_source: schedule.recipient_source,
  };
}

function formToPayload(form: FormState): WorkflowSchedulePayload {
  return {
    frequency: form.frequency,
    timezone: form.timezone,
    recipient_source: form.recipient_source,
    is_active: true,
    ...(form.frequency === "once" ? { run_at: form.run_at } : {}),
    ...(form.frequency !== "once" ? { time_of_day: form.time_of_day } : {}),
    ...(form.frequency === "weekly" ? { weekdays: form.weekdays } : {}),
    ...(form.frequency === "monthly" ? { day_of_month: form.day_of_month } : {}),
  };
}

function describeSchedule(schedule: WorkflowSchedule): string {
  const tz = schedule.timezone;
  switch (schedule.frequency) {
    case "once": {
      const when = schedule.run_at ? new Date(schedule.run_at).toLocaleString() : "an unspecified time";
      return `Once on ${when}`;
    }
    case "daily":
      return `Every day at ${schedule.time_of_day ?? "?"} ${tz}`;
    case "weekly": {
      const days = (schedule.weekdays ?? []).map((d) => WEEKDAY_LABELS[d] ?? "?").join(", ");
      return `Every ${days || "week"} at ${schedule.time_of_day ?? "?"} ${tz}`;
    }
    case "monthly":
      return `Monthly on day ${schedule.day_of_month ?? "?"} at ${schedule.time_of_day ?? "?"} ${tz}`;
    default:
      return "Schedule";
  }
}

export function SchedulePanel({ workflowId, onClose }: SchedulePanelProps) {
  const queryClient = useQueryClient();
  const { data: schedules = [], isLoading } = useQuery({
    queryKey: ["workflow-schedules", workflowId],
    queryFn: () => listSchedules(workflowId),
  });
  const { data: modules = [] } = useQuery({ queryKey: ["workflow-modules"], queryFn: listModules });

  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  function resetForm() {
    setEditingId(null);
    setForm(EMPTY_FORM);
  }

  function startEdit(schedule: WorkflowSchedule) {
    setEditingId(schedule.id);
    setForm(scheduleToForm(schedule));
  }

  const saveMutation = useMutation({
    mutationFn: () =>
      editingId
        ? updateSchedule(workflowId, editingId, formToPayload(form))
        : createSchedule(workflowId, formToPayload(form)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflow-schedules", workflowId] });
      resetForm();
    },
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updateSchedule(workflowId, id, { is_active }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["workflow-schedules", workflowId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteSchedule(workflowId, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflow-schedules", workflowId] });
      setPendingDeleteId(null);
    },
  });

  // A schedule being edited may disappear out from under the form (deleted
  // elsewhere, or this panel reopened) - fall back to a fresh "new
  // schedule" form rather than silently keeping stale edits targeting a
  // schedule id that no longer exists.
  useEffect(() => {
    if (editingId && !schedules.some((s) => s.id === editingId)) resetForm();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schedules]);

  function toggleWeekday(day: number) {
    setForm((f) => ({
      ...f,
      weekdays: f.weekdays.includes(day) ? f.weekdays.filter((d) => d !== day) : [...f.weekdays, day].sort(),
    }));
  }

  return (
    <div className="absolute right-[17rem] top-4 z-10 w-96 max-h-[80vh] overflow-y-auto">
      <Card className="shadow-lg">
        <CardHeader className="flex-row items-center justify-between gap-2 py-3">
          <CardTitle className="text-sm">Schedule</CardTitle>
          <button type="button" className="text-xs text-muted-foreground hover:text-foreground" onClick={onClose}>
            Close
          </button>
        </CardHeader>
        <CardContent className="flex flex-col gap-3 pt-0">
          <div className="flex flex-col gap-2">
            <label className="text-xs font-medium text-foreground">Run</label>
            <div className="flex gap-1.5">
              {(["once", "daily", "weekly", "monthly"] as ScheduleFrequency[]).map((freq) => (
                <button
                  key={freq}
                  type="button"
                  className={cn(segmentBase, form.frequency === freq ? segmentActive : segmentInactive)}
                  onClick={() => setForm((f) => ({ ...f, frequency: freq }))}
                >
                  {freq[0].toUpperCase() + freq.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {form.frequency === "once" && (
            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">Date and time</label>
              <Input
                type="datetime-local"
                value={form.run_at}
                onChange={(e) => setForm((f) => ({ ...f, run_at: e.target.value }))}
              />
            </div>
          )}

          {form.frequency !== "once" && (
            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">Time of day</label>
              <Input
                type="time"
                value={form.time_of_day}
                onChange={(e) => setForm((f) => ({ ...f, time_of_day: e.target.value }))}
              />
            </div>
          )}

          {form.frequency === "weekly" && (
            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">On these days</label>
              <div className="flex gap-1">
                {WEEKDAY_LABELS.map((label, day) => (
                  <button
                    key={label}
                    type="button"
                    className={cn(
                      "flex-1 rounded-md border px-1 py-1 text-[11px] font-medium",
                      form.weekdays.includes(day) ? segmentActive : segmentInactive,
                    )}
                    onClick={() => toggleWeekday(day)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {form.frequency === "monthly" && (
            <div className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">Day of month</label>
              <Input
                type="number"
                min={1}
                max={31}
                value={form.day_of_month}
                onChange={(e) => setForm((f) => ({ ...f, day_of_month: Number(e.target.value) || 1 }))}
              />
              <p className="text-[11px] text-muted-foreground">
                If a month is shorter, this runs on the last day of that month.
              </p>
            </div>
          )}

          <div className="flex flex-col gap-1">
            <label className="text-[11px] text-muted-foreground">Timezone</label>
            <select
              className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
              value={form.timezone}
              onChange={(e) => setForm((f) => ({ ...f, timezone: e.target.value }))}
            >
              {TIMEZONES.map((tz) => (
                <option key={tz} value={tz}>
                  {tz}
                </option>
              ))}
            </select>
          </div>

          <div className="flex flex-col gap-1">
            <label className="text-xs font-medium text-foreground">Recipients</label>
            <RecipientSourceField
              value={form.recipient_source}
              onChange={(next) => setForm((f) => ({ ...f, recipient_source: next }))}
              modules={modules}
            />
          </div>

          <div className="flex items-center gap-2">
            <Button size="sm" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
              {saveMutation.isPending ? "Saving..." : editingId ? "Update schedule" : "Save schedule"}
            </Button>
            {editingId && (
              <Button type="button" variant="outline" size="sm" onClick={resetForm}>
                Cancel edit
              </Button>
            )}
          </div>
          {saveMutation.isError && (
            <p className="text-xs text-destructive">Couldn't save the schedule - please check the fields above.</p>
          )}

          <div className="mt-2 flex flex-col gap-2 border-t border-border pt-3">
            <p className="text-xs font-medium text-foreground">Existing schedules</p>
            {isLoading && <p className="text-xs text-muted-foreground">Loading...</p>}
            {!isLoading && schedules.length === 0 && (
              <p className="text-xs text-muted-foreground">No schedules yet - set one up above.</p>
            )}
            {schedules.map((schedule) => (
              <div key={schedule.id} className="flex flex-col gap-1.5 rounded-md border border-border p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs text-foreground">{describeSchedule(schedule)}</span>
                  <Badge variant={schedule.is_active ? "success" : "outline"}>
                    {schedule.is_active ? "Active" : "Paused"}
                  </Badge>
                </div>
                {schedule.last_run_status && (
                  <p className="text-[11px] text-muted-foreground">Last run: {schedule.last_run_status}</p>
                )}
                <div className="flex items-center gap-1.5">
                  <Button type="button" variant="outline" size="sm" onClick={() => startEdit(schedule)}>
                    Edit
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      toggleActiveMutation.mutate({ id: schedule.id, is_active: !schedule.is_active })
                    }
                    disabled={toggleActiveMutation.isPending}
                  >
                    {schedule.is_active ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
                    {schedule.is_active ? "Pause" : "Resume"}
                  </Button>
                  {pendingDeleteId === schedule.id ? (
                    <>
                      <Button
                        type="button"
                        variant="destructive"
                        size="sm"
                        onClick={() => deleteMutation.mutate(schedule.id)}
                        disabled={deleteMutation.isPending}
                      >
                        {deleteMutation.isPending ? "Deleting..." : "Confirm delete"}
                      </Button>
                      <button
                        type="button"
                        aria-label="Cancel delete"
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted"
                        onClick={() => setPendingDeleteId(null)}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      aria-label="Delete schedule"
                      className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
                      onClick={() => setPendingDeleteId(schedule.id)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
