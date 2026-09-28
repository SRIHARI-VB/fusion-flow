import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";
import { useSetPageTitle } from "../../components/layout/page-title";
import { listDoctors, listHistory } from "./api";
import { PAYMENT_MODE_LABELS, type HistoryFilters, type PaymentMode } from "./types";

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function formatAmount(value: number | null): string {
  return value === null ? "—" : value.toLocaleString(undefined, { style: "currency", currency: "INR" });
}

/** Truncates long consultation notes inline, with the full text on hover/
 * click via the native `title` attribute - no dedicated tooltip component
 * exists in `@fusion-flow/ui` today, and `title` is a zero-dependency way
 * to avoid either silently overflowing the table or building one just for
 * this single column. */
function NotesCell({ notes }: { notes: string }) {
  const truncated = notes.length > 60 ? `${notes.slice(0, 60)}…` : notes;
  return (
    <span title={notes} className="cursor-help">
      {truncated}
    </span>
  );
}

export function HistoryPage() {
  useSetPageTitle("Patient Visit History");

  const [filters, setFilters] = useState<HistoryFilters>({});

  const { data: doctors = [] } = useQuery({ queryKey: ["clinic-queue", "doctors"], queryFn: listDoctors });

  const {
    data: visits = [],
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["clinic-queue", "history", filters],
    queryFn: () => listHistory(filters),
  });

  // Notes visibility is per-requesting-user, not per-row - the backend
  // either includes `consultation_notes` on every completed visit or on
  // none of them, so checking the first row is sufficient and avoids a
  // frontend-only role check duplicating what the backend already enforces.
  const showNotesColumn = useMemo(() => visits.length > 0 && "consultation_notes" in visits[0], [visits]);

  function updateFilter<K extends keyof HistoryFilters>(key: K, value: HistoryFilters[K]) {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Patient Visit History</h1>
        <p className="text-sm text-muted-foreground">Completed visits, filterable by date, doctor, and payment mode.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="date_from" className="text-sm font-medium">
                From
              </label>
              <Input
                id="date_from"
                type="date"
                value={filters.date_from ?? ""}
                onChange={(e) => updateFilter("date_from", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="date_to" className="text-sm font-medium">
                To
              </label>
              <Input
                id="date_to"
                type="date"
                value={filters.date_to ?? ""}
                onChange={(e) => updateFilter("date_to", e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="doctor_filter" className="text-sm font-medium">
                Doctor
              </label>
              <select
                id="doctor_filter"
                className="flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={filters.doctor_membership_id ?? ""}
                onChange={(e) => updateFilter("doctor_membership_id", e.target.value)}
              >
                <option value="">All doctors</option>
                {doctors.map((doctor) => (
                  <option key={doctor.membership_id} value={doctor.membership_id}>
                    {doctor.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="payment_mode_filter" className="text-sm font-medium">
                Payment mode
              </label>
              <select
                id="payment_mode_filter"
                className="flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={filters.payment_mode ?? ""}
                onChange={(e) => updateFilter("payment_mode", (e.target.value || undefined) as PaymentMode | undefined)}
              >
                <option value="">All</option>
                {Object.entries(PAYMENT_MODE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Visits</CardTitle>
          <CardDescription>{visits.length} completed visit{visits.length === 1 ? "" : "s"} in range.</CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {isError && <p className="text-sm text-destructive">Could not load visit history.</p>}
          {!isLoading && !isError && visits.length === 0 && (
            <p className="text-sm text-muted-foreground">No completed visits match these filters.</p>
          )}
          {!isLoading && !isError && visits.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Patient</TableHead>
                  <TableHead>Doctor</TableHead>
                  <TableHead>Checked in</TableHead>
                  <TableHead>Completed</TableHead>
                  <TableHead>Amount collected</TableHead>
                  <TableHead>Payment</TableHead>
                  {showNotesColumn && <TableHead>Consultation notes</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {visits.map((visit) => (
                  <TableRow key={visit.id}>
                    <TableCell>
                      <div className="flex flex-col">
                        <span className="font-medium text-foreground">{visit.customer_name}</span>
                        <span className="text-xs text-muted-foreground">{visit.customer_phone ?? "—"}</span>
                      </div>
                    </TableCell>
                    <TableCell>{visit.assigned_doctor_name ?? "—"}</TableCell>
                    <TableCell>{formatDateTime(visit.checked_in_at)}</TableCell>
                    <TableCell>{formatDateTime(visit.completed_at)}</TableCell>
                    <TableCell>{formatAmount(visit.amount_collected)}</TableCell>
                    <TableCell>
                      {visit.payment_mode ? (
                        <Badge variant="secondary">{PAYMENT_MODE_LABELS[visit.payment_mode]}</Badge>
                      ) : (
                        "—"
                      )}
                    </TableCell>
                    {showNotesColumn && (
                      <TableCell>
                        {visit.consultation_notes ? <NotesCell notes={visit.consultation_notes} /> : "—"}
                      </TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
