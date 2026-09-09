import { useQuery } from "@tanstack/react-query";
import {
  Badge,
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  type BadgeVariant,
} from "@fusion-flow/ui";
import { listPayments } from "./api";
import type { PaymentStatus } from "./types";

const statusVariant: Record<PaymentStatus, BadgeVariant> = {
  pending: "outline",
  succeeded: "success",
  failed: "destructive",
  refunded: "secondary",
};

export function PaymentsPage() {
  const { data: payments = [], isLoading } = useQuery({ queryKey: ["payments"], queryFn: listPayments });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Payments</h1>
        <p className="text-sm text-muted-foreground">
          Payments recorded by your connectors. This view is read-only — payments are created
          automatically once a payment connector is live.
        </p>
      </div>

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Provider ref</TableHead>
              <TableHead>Amount</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Date</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && payments.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  No payments yet.
                </TableCell>
              </TableRow>
            )}
            {payments.map((payment) => (
              <TableRow key={payment.id}>
                <TableCell className="font-medium text-foreground">
                  {payment.provider_ref ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
                <TableCell>
                  {payment.currency} {payment.amount}
                </TableCell>
                <TableCell>
                  <Badge variant={statusVariant[payment.status]}>{payment.status}</Badge>
                </TableCell>
                <TableCell>{new Date(payment.created_at).toLocaleDateString()}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
