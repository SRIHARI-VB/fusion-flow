import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@fusion-flow/ui";
import { CalendarView } from "./CalendarView";
import { UpcomingListView } from "./UpcomingListView";
import { normalizeAppointment } from "./appointmentHelpers";
import { ModuleAccessNotice } from "../../components/auth/ModuleAccessNotice";
import { useModuleAccess } from "../../lib/useModuleAccess";
import { getCustomersByIds, listObjectRecords } from "./api";

/**
 * The business-object type `key` this page renders records for (see
 * `fusionflow.modules.business_objects`) - records are created by the
 * clinic's booking chatbot workflow, not by hand here, so there's no
 * create/edit/delete UI, just calendar/list views.
 */
const OBJECT_TYPE_KEY = "appointment";

type ViewMode = "calendar" | "list";

/** Read-only viewer for a tenant's "appointment" business-object records. */
export function AppointmentRecordsPage() {
  const [view, setView] = useState<ViewMode>("calendar");
  // Legacy records show a customer name resolved via /customers; skip that
  // lookup (and say so) when the Customers module isn't accessible.
  const { isGranted } = useModuleAccess();
  const customersAvailable = isGranted("customers");

  const { data: records = [], isLoading: recordsLoading } = useQuery({
    queryKey: ["business-objects", "records", OBJECT_TYPE_KEY],
    queryFn: () => listObjectRecords(OBJECT_TYPE_KEY),
  });

  const customerIds = records.map((record) => record.customer_id).filter((id): id is string => Boolean(id));

  const { data: customersById } = useQuery({
    queryKey: ["customers", "batch", customerIds.slice().sort().join(",")],
    queryFn: () => getCustomersByIds(customerIds),
    enabled: customerIds.length > 0 && customersAvailable,
  });

  function customerLabel(customerId: string | null): string {
    if (!customerId) return "—";
    if (!customersAvailable) return "Customer hidden";
    const customer = customersById?.get(customerId);
    if (customer === undefined) return "Loading…";
    if (customer === null) return customerId;
    return customer.name || customerId;
  }

  // Only legacy records (no `customer_name` field) ever fall through to
  // `customerLabel`, so this only refetches/rebuilds when it can actually
  // change something on screen.
  const appointments = useMemo(
    () => records.map((record) => normalizeAppointment(record, customerLabel)),
    [records, customersById, customersAvailable],
  );

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Appointments</h1>
          <p className="text-sm text-muted-foreground">Bookings created by your chatbot workflows.</p>
        </div>
        <div className="inline-flex gap-1 rounded-md border border-border bg-card p-1">
          <Button
            type="button"
            size="sm"
            variant={view === "calendar" ? "default" : "ghost"}
            onClick={() => setView("calendar")}
          >
            Calendar
          </Button>
          <Button type="button" size="sm" variant={view === "list" ? "default" : "ghost"} onClick={() => setView("list")}>
            Upcoming
          </Button>
        </div>
      </div>

      {recordsLoading ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
          Loading…
        </div>
      ) : view === "calendar" ? (
        <CalendarView appointments={appointments} />
      ) : (
        <UpcomingListView appointments={appointments} />
      )}
    </div>
  );
}
