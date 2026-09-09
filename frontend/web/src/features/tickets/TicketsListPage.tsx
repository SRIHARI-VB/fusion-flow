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
import { createTicket, listTickets } from "./api";
import type { TicketStatus } from "./types";

const statusVariant: Record<TicketStatus, BadgeVariant> = {
  open: "default",
  pending: "outline",
  resolved: "success",
  closed: "secondary",
};

const ticketSchema = z.object({
  subject: z.string().min(1, "Subject is required"),
  customer_id: z.string().optional(),
  priority: z.string().min(1).max(20),
});

type TicketFormValues = z.infer<typeof ticketSchema>;

export function TicketsListPage() {
  const queryClient = useQueryClient();
  const [formOpen, setFormOpen] = useState(false);

  const { data: tickets = [], isLoading } = useQuery({ queryKey: ["tickets"], queryFn: listTickets });
  const { data: customers = [] } = useQuery({ queryKey: ["customers"], queryFn: listCustomers });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<TicketFormValues>({
    resolver: zodResolver(ticketSchema),
    defaultValues: { subject: "", customer_id: "", priority: "medium" },
  });

  const createMutation = useMutation({
    mutationFn: createTicket,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tickets"] });
      setFormOpen(false);
      reset({ subject: "", customer_id: "", priority: "medium" });
    },
  });

  function onSubmit(values: TicketFormValues) {
    createMutation.mutate({
      subject: values.subject,
      priority: values.priority,
      customer_id: values.customer_id || null,
    });
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Tickets</h1>
          <p className="text-sm text-muted-foreground">Support conversations with your customers.</p>
        </div>
        <Button onClick={() => setFormOpen((open) => !open)}>
          <Plus className="h-4 w-4" />
          New Ticket
        </Button>
      </div>

      {formOpen && (
        <Card>
          <CardHeader>
            <CardTitle>New ticket</CardTitle>
            <CardDescription>Open a support ticket manually.</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="flex flex-col gap-1.5 sm:col-span-2">
                <label htmlFor="subject" className="text-sm font-medium">
                  Subject
                </label>
                <Input id="subject" error={!!errors.subject} {...register("subject")} />
                {errors.subject && <p className="text-xs text-destructive">{errors.subject.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="customer_id" className="text-sm font-medium">
                  Customer
                </label>
                <select
                  id="customer_id"
                  className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
                  {...register("customer_id")}
                >
                  <option value="">Unassigned</option>
                  {customers.map((customer) => (
                    <option key={customer.id} value={customer.id}>
                      {customer.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="priority" className="text-sm font-medium">
                  Priority
                </label>
                <select
                  id="priority"
                  className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
                  {...register("priority")}
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="urgent">Urgent</option>
                </select>
              </div>
              <div className="flex items-center gap-2 sm:col-span-2">
                <Button type="submit" disabled={createMutation.isPending}>
                  {createMutation.isPending ? "Creating..." : "Create ticket"}
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
              <TableHead>Subject</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Priority</TableHead>
              <TableHead>Customer</TableHead>
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
            {!isLoading && tickets.length === 0 && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-muted-foreground">
                  No tickets yet.
                </TableCell>
              </TableRow>
            )}
            {tickets.map((ticket) => (
              <TableRow key={ticket.id}>
                <TableCell>
                  <Link
                    to={`/tickets/${ticket.id}`}
                    className="font-medium text-foreground hover:text-accent"
                  >
                    {ticket.subject}
                  </Link>
                </TableCell>
                <TableCell>
                  <Badge variant={statusVariant[ticket.status]}>{ticket.status}</Badge>
                </TableCell>
                <TableCell className="capitalize">{ticket.priority}</TableCell>
                <TableCell>
                  {ticket.customer_name ?? <span className="text-muted-foreground">—</span>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
