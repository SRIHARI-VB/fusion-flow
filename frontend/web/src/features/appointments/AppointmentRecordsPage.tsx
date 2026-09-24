import { useQuery } from "@tanstack/react-query";
import {
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";
import { DynamicCustomFieldsCells, DynamicCustomFieldsColumns } from "../custom-fields";
import { fetchObjectType, getCustomersByIds, listObjectFieldDefinitions, listObjectRecords } from "./api";
import { toDisplayFieldDefinition } from "./types";

/**
 * The business-object type `key` this page renders. Everything below reads
 * field definitions/records generically off whatever type this points at -
 * lift this component (and swap the key) to view a different tenant-defined
 * object type's records.
 */
const OBJECT_TYPE_KEY = "appointment";

/** Read-only viewer for a tenant's "appointment" business-object records
 * (see `fusionflow.modules.business_objects`) - these are created by the
 * clinic's booking chatbot workflow, not by hand here, so there's no
 * create/edit/delete UI, just a list. */
export function AppointmentRecordsPage() {
  const { data: objectType, isLoading: typeLoading } = useQuery({
    queryKey: ["business-objects", "type", OBJECT_TYPE_KEY],
    queryFn: () => fetchObjectType(OBJECT_TYPE_KEY),
  });

  const { data: fieldDefinitions = [], isLoading: fieldsLoading } = useQuery({
    queryKey: ["business-objects", "fields", objectType?.id],
    queryFn: () => listObjectFieldDefinitions(objectType!.id),
    enabled: !!objectType,
  });

  const { data: records = [], isLoading: recordsLoading } = useQuery({
    queryKey: ["business-objects", "records", OBJECT_TYPE_KEY],
    queryFn: () => listObjectRecords(OBJECT_TYPE_KEY),
  });

  const customerIds = records.map((record) => record.customer_id).filter((id): id is string => Boolean(id));

  const { data: customersById } = useQuery({
    queryKey: ["customers", "batch", customerIds.slice().sort().join(",")],
    queryFn: () => getCustomersByIds(customerIds),
    enabled: customerIds.length > 0,
  });

  const displayFieldDefinitions = fieldDefinitions.map(toDisplayFieldDefinition);
  const isLoading = typeLoading || fieldsLoading || recordsLoading;
  const columnCount = displayFieldDefinitions.length + 2; // + Customer, Created

  function customerLabel(customerId: string | null): string {
    if (!customerId) return "—";
    const customer = customersById?.get(customerId);
    if (customer === undefined) return "Loading…";
    if (customer === null) return customerId;
    return customer.name || customerId;
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Appointments</h1>
        <p className="text-sm text-muted-foreground">Bookings created by your chatbot workflows.</p>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <DynamicCustomFieldsColumns definitions={displayFieldDefinitions} />
              <TableHead>Customer</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={columnCount} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && records.length === 0 && (
              <TableRow>
                <TableCell colSpan={columnCount} className="text-center text-muted-foreground">
                  No appointments yet.
                </TableCell>
              </TableRow>
            )}
            {!isLoading &&
              records.map((record) => (
                <TableRow key={record.id}>
                  <DynamicCustomFieldsCells definitions={displayFieldDefinitions} values={record.payload} />
                  <TableCell className="text-sm text-muted-foreground">
                    {customerLabel(record.customer_id)}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(record.created_at).toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
