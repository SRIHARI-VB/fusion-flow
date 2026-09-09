import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Pencil, Plus, Trash2, X } from "lucide-react";
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
} from "@fusion-flow/ui";
import { createCustomer, deleteCustomer, listCustomers, updateCustomer } from "./api";
import type { Customer } from "./types";

const customerSchema = z.object({
  name: z.string().min(1, "Name is required"),
  email: z.string().email("Enter a valid email").optional().or(z.literal("")),
  phone: z.string().optional().or(z.literal("")),
  external_ref: z.string().optional().or(z.literal("")),
});

type CustomerFormValues = z.infer<typeof customerSchema>;

export function CustomersPage() {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Customer | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const { data: customers = [], isLoading } = useQuery({
    queryKey: ["customers"],
    queryFn: listCustomers,
  });

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CustomerFormValues>({ resolver: zodResolver(customerSchema) });

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
  }

  const createMutation = useMutation({
    mutationFn: createCustomer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      closeForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: CustomerUpdateArgs }) =>
      updateCustomer(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["customers"] });
      closeForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCustomer,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["customers"] }),
  });

  function openCreate() {
    setEditing(null);
    reset({ name: "", email: "", phone: "", external_ref: "" });
    setFormOpen(true);
  }

  function openEdit(customer: Customer) {
    setEditing(customer);
    reset({
      name: customer.name,
      email: customer.email ?? "",
      phone: customer.phone ?? "",
      external_ref: customer.external_ref ?? "",
    });
    setFormOpen(true);
  }

  function onSubmit(values: CustomerFormValues) {
    const payload = {
      name: values.name,
      email: values.email || null,
      phone: values.phone || null,
      external_ref: values.external_ref || null,
    };
    if (editing) {
      updateMutation.mutate({ id: editing.id, payload });
    } else {
      createMutation.mutate(payload);
    }
  }

  const saving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Customers</h1>
          <p className="text-sm text-muted-foreground">Everyone who has ever bought from or messaged you.</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4" />
          New Customer
        </Button>
      </div>

      {formOpen && (
        <Card>
          <CardHeader>
            <CardTitle>{editing ? "Edit customer" : "New customer"}</CardTitle>
            <CardDescription>
              {editing ? "Update this customer's details." : "Add a customer record manually."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="name" className="text-sm font-medium">
                  Name
                </label>
                <Input id="name" error={!!errors.name} {...register("name")} />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="email" className="text-sm font-medium">
                  Email
                </label>
                <Input id="email" type="email" error={!!errors.email} {...register("email")} />
                {errors.email && <p className="text-xs text-destructive">{errors.email.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="phone" className="text-sm font-medium">
                  Phone
                </label>
                <Input id="phone" {...register("phone")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="external_ref" className="text-sm font-medium">
                  External reference
                </label>
                <Input id="external_ref" {...register("external_ref")} />
              </div>
              <div className="flex items-center gap-2 sm:col-span-2">
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving..." : editing ? "Save changes" : "Create customer"}
                </Button>
                <Button type="button" variant="outline" onClick={closeForm}>
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
              <TableHead>Name</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>External ref</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && customers.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  No customers yet.
                </TableCell>
              </TableRow>
            )}
            {customers.map((customer) => (
              <TableRow key={customer.id}>
                <TableCell className="font-medium text-foreground">{customer.name}</TableCell>
                <TableCell>{customer.email ?? <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell>{customer.phone ?? <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell>
                  {customer.external_ref ? (
                    <Badge variant="outline">{customer.external_ref}</Badge>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(customer)} aria-label="Edit">
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => deleteMutation.mutate(customer.id)}
                      aria-label="Delete"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}

type CustomerUpdateArgs = Parameters<typeof updateCustomer>[1];
