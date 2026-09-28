import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";
import { useSetPageTitle } from "../../components/layout/page-title";
import { getOrder, updateOrder } from "./api";
import type { OrderStatus } from "./types";

const statuses: OrderStatus[] = ["pending", "paid", "fulfilled", "cancelled"];

export function OrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const queryClient = useQueryClient();

  const { data: order, isLoading } = useQuery({
    queryKey: ["orders", id],
    queryFn: () => getOrder(id as string),
    enabled: !!id,
  });
  useSetPageTitle(order ? `Order for ${order.customer_name ?? order.customer_id}` : null);

  const statusMutation = useMutation({
    mutationFn: (status: OrderStatus) => updateOrder(id as string, { status }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders", id] });
      queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
  });

  if (isLoading || !order) {
    return <p className="text-sm text-muted-foreground">Loading...</p>;
  }

  const lineItems = order.line_items ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          to="/orders"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" />
          Back to orders
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-foreground">
          Order for {order.customer_name ?? order.customer_id}
        </h1>
        <p className="text-sm text-muted-foreground">
          Placed {new Date(order.created_at).toLocaleString()}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader>
            <CardDescription>Status</CardDescription>
            <select
              className="mt-1 h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground"
              value={order.status}
              onChange={(event) => statusMutation.mutate(event.target.value as OrderStatus)}
            >
              {statuses.map((statusOption) => (
                <option key={statusOption} value={statusOption}>
                  {statusOption}
                </option>
              ))}
            </select>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Total</CardDescription>
            <CardTitle>
              {order.currency} {order.total_amount}
            </CardTitle>
          </CardHeader>
        </Card>
        <Card>
          <CardHeader>
            <CardDescription>Currency</CardDescription>
            <CardTitle>{order.currency}</CardTitle>
          </CardHeader>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Line items</CardTitle>
          <CardDescription>Contents of this order's line items.</CardDescription>
        </CardHeader>
        <CardContent>
          {lineItems.length === 0 ? (
            <p className="text-sm text-muted-foreground">No line items recorded.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Item</TableHead>
                  <TableHead>Qty</TableHead>
                  <TableHead>Price</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lineItems.map((item, index) => (
                  <TableRow key={index}>
                    <TableCell>{String(item.name ?? item.title ?? JSON.stringify(item))}</TableCell>
                    <TableCell>{String(item.quantity ?? item.qty ?? "—")}</TableCell>
                    <TableCell>{String(item.price ?? item.amount ?? "—")}</TableCell>
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
