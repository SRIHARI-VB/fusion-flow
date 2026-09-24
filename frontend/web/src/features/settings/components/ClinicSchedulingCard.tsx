import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { CalendarClock } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import {
  type ClinicSettingsPayload,
  createClinicSettingsRecord,
  fetchClinicSettingsRecord,
  updateClinicSettingsRecord,
} from "../clinic-settings-api";

const WEEKDAYS = [
  { value: "monday", label: "Mon" },
  { value: "tuesday", label: "Tue" },
  { value: "wednesday", label: "Wed" },
  { value: "thursday", label: "Thu" },
  { value: "friday", label: "Fri" },
  { value: "saturday", label: "Sat" },
  { value: "sunday", label: "Sun" },
] as const;

const TIME_PATTERN = /^([01]\d|2[0-3]):[0-5]\d$/;
const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

const timeField = z.string().regex(TIME_PATTERN, "Use 24-hour HH:MM, e.g. 09:00");
const optionalTimeField = z
  .string()
  .refine((value) => value === "" || TIME_PATTERN.test(value), "Use 24-hour HH:MM, e.g. 13:00 — or leave blank");

const clinicSchedulingSchema = z.object({
  business_name: z.string().min(1, "Business name is required"),
  phone: z.string().min(1, "Phone is required"),
  address: z.string().min(1, "Address is required"),
  open_time: timeField,
  close_time: timeField,
  closed_weekdays: z.array(z.string()),
  morning_start: timeField,
  morning_end: timeField,
  afternoon_start: timeField,
  afternoon_end: timeField,
  evening_start: timeField,
  evening_end: timeField,
  break_start: optionalTimeField,
  break_end: optionalTimeField,
  direct_booking_weekdays: z.array(z.string()),
  direct_booking_specific_dates: z.string().refine((value) => {
    const dates = value
      .split(",")
      .map((d) => d.trim())
      .filter(Boolean);
    return dates.every((d) => DATE_PATTERN.test(d));
  }, "Use comma-separated YYYY-MM-DD dates, e.g. 2026-01-01, 2026-01-15"),
});

type ClinicSchedulingFormValues = z.infer<typeof clinicSchedulingSchema>;

const EMPTY_VALUES: ClinicSchedulingFormValues = {
  business_name: "",
  phone: "",
  address: "",
  open_time: "",
  close_time: "",
  closed_weekdays: [],
  morning_start: "",
  morning_end: "",
  afternoon_start: "",
  afternoon_end: "",
  evening_start: "",
  evening_end: "",
  break_start: "",
  break_end: "",
  direct_booking_weekdays: [],
  direct_booking_specific_dates: "",
};

function toFormValues(payload: Partial<ClinicSettingsPayload> | undefined): ClinicSchedulingFormValues {
  return {
    ...EMPTY_VALUES,
    ...payload,
    closed_weekdays: payload?.closed_weekdays ?? [],
    direct_booking_weekdays: payload?.direct_booking_weekdays ?? [],
  };
}

interface WeekdayCheckboxesProps {
  value: string[];
  onChange: (next: string[]) => void;
  idPrefix: string;
}

function WeekdayCheckboxes({ value, onChange, idPrefix }: WeekdayCheckboxesProps) {
  return (
    <div className="flex flex-wrap gap-4">
      {WEEKDAYS.map((day) => {
        const checked = value.includes(day.value);
        const id = `${idPrefix}-${day.value}`;
        return (
          <label key={day.value} htmlFor={id} className="flex items-center gap-1.5 text-sm text-foreground">
            <input
              id={id}
              type="checkbox"
              className="h-4 w-4 rounded border-input accent-accent"
              checked={checked}
              onChange={(event) => {
                onChange(
                  event.target.checked ? [...value, day.value] : value.filter((d) => d !== day.value),
                );
              }}
            />
            {day.label}
          </label>
        );
      })}
    </div>
  );
}

/**
 * "Clinic scheduling" settings — reads/writes the tenant's single
 * `business_settings` custom-object record (see `clinic-settings-api.ts`).
 * A bespoke, hardcoded-field form rather than a generic record editor,
 * matching the plan's call that this doesn't need field-definition-driven
 * rendering: it's one fixed shape the booking flow already depends on.
 */
export function ClinicSchedulingCard({ businessId }: { businessId: string | null }) {
  const queryClient = useQueryClient();
  const queryKey = ["settings", "clinic-scheduling", businessId];

  const {
    data: record,
    isLoading,
    isError: loadError,
  } = useQuery({
    queryKey,
    queryFn: fetchClinicSettingsRecord,
    enabled: !!businessId,
  });

  const {
    register,
    handleSubmit,
    reset,
    control,
    formState: { errors },
  } = useForm<ClinicSchedulingFormValues>({
    resolver: zodResolver(clinicSchedulingSchema),
    defaultValues: EMPTY_VALUES,
  });

  useEffect(() => {
    if (record) reset(toFormValues(record.payload));
  }, [record, reset]);

  const saveMutation = useMutation({
    mutationFn: (values: ClinicSchedulingFormValues) => {
      const payload: ClinicSettingsPayload = { ...values };
      return record ? updateClinicSettingsRecord(record.id, payload) : createClinicSettingsRecord(payload);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKey, updated);
    },
  });

  function timeInput(name: keyof ClinicSchedulingFormValues & string, label: string, placeholder: string) {
    const error = errors[name]?.message as string | undefined;
    return (
      <div className="flex flex-col gap-1.5">
        <label htmlFor={name} className="text-sm font-medium">
          {label}
        </label>
        <Input id={name} placeholder={placeholder} error={!!error} {...register(name)} />
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <CalendarClock className="h-5 w-5" />
          Clinic scheduling
        </CardTitle>
        <CardDescription>
          Working hours, booking time windows, and which days get auto-confirmed bookings. This
          feeds the booking flow directly.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
        {loadError && (
          <p className="text-sm text-destructive">Could not load clinic scheduling settings.</p>
        )}
        {!isLoading && !loadError && (
          <form
            className="flex flex-col gap-6"
            onSubmit={handleSubmit((values) => saveMutation.mutate(values))}
            noValidate
          >
            {/* Contact & location */}
            <div className="flex flex-col gap-4">
              <h3 className="text-sm font-semibold text-foreground">Contact & location</h3>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="business_name" className="text-sm font-medium">
                    Business name
                  </label>
                  <Input id="business_name" error={!!errors.business_name} {...register("business_name")} />
                  {errors.business_name && (
                    <p className="text-xs text-destructive">{errors.business_name.message}</p>
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="phone" className="text-sm font-medium">
                    Phone
                  </label>
                  <Input id="phone" error={!!errors.phone} {...register("phone")} />
                  {errors.phone && <p className="text-xs text-destructive">{errors.phone.message}</p>}
                </div>
                <div className="flex flex-col gap-1.5 sm:col-span-2">
                  <label htmlFor="address" className="text-sm font-medium">
                    Address
                  </label>
                  <Input id="address" error={!!errors.address} {...register("address")} />
                  {errors.address && <p className="text-xs text-destructive">{errors.address.message}</p>}
                </div>
              </div>
            </div>

            {/* Working hours */}
            <div className="flex flex-col gap-4 border-t border-border pt-4">
              <h3 className="text-sm font-semibold text-foreground">Working hours</h3>
              <div className="grid gap-4 sm:grid-cols-2">
                {timeInput("open_time", "Open time", "09:00")}
                {timeInput("close_time", "Close time", "18:00")}
              </div>
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">Fully closed weekdays</span>
                <Controller
                  control={control}
                  name="closed_weekdays"
                  render={({ field }) => (
                    <WeekdayCheckboxes value={field.value} onChange={field.onChange} idPrefix="closed" />
                  )}
                />
              </div>
            </div>

            {/* Time windows */}
            <div className="flex flex-col gap-4 border-t border-border pt-4">
              <h3 className="text-sm font-semibold text-foreground">Time windows</h3>
              <p className="text-xs text-muted-foreground">
                The three booking-flow time-of-day windows customers pick from.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                {timeInput("morning_start", "Morning start", "09:00")}
                {timeInput("morning_end", "Morning end", "12:00")}
                {timeInput("afternoon_start", "Afternoon start", "13:00")}
                {timeInput("afternoon_end", "Afternoon end", "17:00")}
                {timeInput("evening_start", "Evening start", "17:00")}
                {timeInput("evening_end", "Evening end", "20:00")}
              </div>
            </div>

            {/* Break time */}
            <div className="flex flex-col gap-4 border-t border-border pt-4">
              <h3 className="text-sm font-semibold text-foreground">Break time (optional)</h3>
              <p className="text-xs text-muted-foreground">
                Leave both blank if this business doesn't take a daily break.
              </p>
              <div className="grid gap-4 sm:grid-cols-2">
                {timeInput("break_start", "Break start", "13:00")}
                {timeInput("break_end", "Break end", "14:00")}
              </div>
            </div>

            {/* Direct booking days */}
            <div className="flex flex-col gap-4 border-t border-border pt-4">
              <h3 className="text-sm font-semibold text-foreground">Direct booking days</h3>
              <p className="text-xs text-muted-foreground">
                These days get automatically confirmed via calendar instead of needing staff
                review.
              </p>
              <div className="flex flex-col gap-1.5">
                <span className="text-sm font-medium">Recurring weekdays</span>
                <Controller
                  control={control}
                  name="direct_booking_weekdays"
                  render={({ field }) => (
                    <WeekdayCheckboxes value={field.value} onChange={field.onChange} idPrefix="direct" />
                  )}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="direct_booking_specific_dates" className="text-sm font-medium">
                  Specific one-off dates
                </label>
                <Input
                  id="direct_booking_specific_dates"
                  placeholder="2026-01-01, 2026-01-15"
                  error={!!errors.direct_booking_specific_dates}
                  {...register("direct_booking_specific_dates")}
                />
                <p className="text-xs text-muted-foreground">
                  Comma-separated YYYY-MM-DD dates, in addition to the weekday rule above.
                </p>
                {errors.direct_booking_specific_dates && (
                  <p className="text-xs text-destructive">{errors.direct_booking_specific_dates.message}</p>
                )}
              </div>
            </div>

            {saveMutation.isError && (
              <p className="text-sm text-destructive">
                Could not save clinic scheduling settings. Please try again.
              </p>
            )}
            {saveMutation.isSuccess && !saveMutation.isPending && (
              <p className="text-sm text-success">Saved.</p>
            )}
            <div>
              <Button type="submit" disabled={saveMutation.isPending || !businessId}>
                {saveMutation.isPending ? "Saving..." : "Save changes"}
              </Button>
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
