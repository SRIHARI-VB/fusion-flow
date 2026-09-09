import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Link } from "react-router-dom";
import { Plus, X } from "lucide-react";
import {
  Badge,
  Button,
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
  type BadgeVariant,
} from "@fusion-flow/ui";
import { listCustomers } from "../customers/api";
import { createOrder, listOrders } from "./api";
import type { OrderStatus } from "./types";

const statusVariant: Record<OrderStatus, BadgeVariant> = {
  pending: "outline",
  paid: "default",
  fulfilled: "success",
  cancelled: "destructive",
};

const orderSchema = z.object({
  customer_id: z.string().min(1, "Select a customer"),
  status: z.enum(["pending", "paid", "fulfilled", "cancelled"]),
  total_amount: z.coerce.number().min(0, "Must be zero or more"),
  currency: z.string().min(3, "3-letter code").max(3, "3-letter code"),
});

type OrderFormValues = z.infer<typeof orderSchema>;

export function OrdersListPage() {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);

  const { data: orders = [], isLoading } = useQuery({ queryKey: ["orders"], queryFn: listOrders });
  const { data: customers = [] } = useQuery({ queryKey: ["customers"], queryFn: listCustomers });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<OrderFormValues>({
    resolver: zodResolver(orderSchema),
    defaultValues: { customer_id: "", status: "pending", total_amount: 0, currency: "USD" },
  });

  const createMutation = useMutation({
    mutationFn: createOrder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      setFormOpen(false);
      reset({ customer_id: "", status: "pending", total_amount: 0, currency: "USD" });
    },
  });

  function onSubmit(values: OrderFormValues) {
    createMutation.mutate({ ...values, line_items: [] });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Orders</h1>
          <p className="text-sm text-muted-foreground">Every order placed by a customer.</p>
        </div>
        <Button onClick={() => setFormOpen((open) => !open)}>
          <Plus className="h-4 w-4" />
          New Order
        </Button>
      </div>

      {formOpen && (
        <Card>
          <CardHeader>
            <CardTitle>New order</CardTitle>
            <CardDescription>Create an order manually.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="customer_id" className="text-sm font-medium">
                  Customer
                </label>
                <select
                  id="customer_id"
                  className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
                  {...register("customer_id")}
                >
                  <option value="">Select a customer</option>
                  {customers.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name}
                    </option>
                  ))}
                </select>
                {errors.customer_id && (
                  <p className="text-xs text-destructive">{errors.customer_id.message}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="status" className="text-sm font-medium">
                  Status
                </label>
                <select
                  id="status"
                  className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
                  {...register("status")}
                >
                  <option value="pending">Pending</option>
                  <option value="paid">Paid</option>
                  <option value="fulfilled">Fulfilled</option>
                  <option value="cancelled">Cancelled</option>
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="total_amount" className="text-sm font-medium">
                  Total amount
                </label>
                <Input
                  id="total_amount"
                  type="number"
                  step="0.01"
                  error={!!errors.total_amount}
                  {...register("total_amount")}
                />
                {errors.total_amount && (
                  <p className="text-xs text-destructive">{errors.total_amount.message}</p>
                )}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="currency" className="text-sm font-medium">
                  Currency
                </label>
                <Input id="currency" maxLength={3} error={!!errors.currency} {...register("currency")} />
                {errors.currency && <p className="text-xs text-destructive">{errors.currency.message}</p>}
              </div>
              <div className="flex items-center gap-2 sm:col-span-2">
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? "Creating..." : "Create order"}
                </Button>
                <Button type="button" variant="outline" onClick={() => setFormOpen(false)}>
                  <X className="h-4 w-4" />
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Customer</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Total</TableHead>
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
            {!isLoading && orders.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  No orders yet.
                </TableCell>
              </TableRow>
            )}
            {orders.map((order) => (
              <TableRow key={order.id}>
                <TableCell>
                  <Link to={`/orders/${order.id}`} className="font-medium text-foreground hover:text-accent">
                    {order.customer_name ?? order.customer_id}
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant={statusVariant[order.status]}>{order.status}</Badge>
                </TableCell>
                <TableCell>
                  {order.currency} {order.total_amount}
                </TableCell>
                <TableCell>{new Date(order.created_at).toLocaleDateString()}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
