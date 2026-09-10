import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Pencil, Plus, Trash2, X } from "lucide-react";
import {
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
import {
  DynamicCustomFieldsCells,
  DynamicCustomFieldsColumns,
  DynamicCustomFieldsFields,
  useFieldDefinitions,
} from "../custom-fields";
import { createOffer, deleteOffer, listOffers, updateOffer } from "./api";
import type { Offer } from "./types";

interface FormValues {
  name: string;
  applies_to_json: string;
  active_from: string;
  active_to: string;
  custom_fields: Record<string, unknown>;
}

const DEFAULT_VALUES: FormValues = {
  name: "",
  applies_to_json: "{}",
  active_from: "",
  active_to: "",
  custom_fields: {},
};

function toDatetimeLocal(iso: string | null): string {
  if (!iso) return "";
  return iso.slice(0, 16);
}

function toIsoOrNull(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

export function OffersPage() {
  const queryClient = useQueryClient();
  const queryKey = ["offers"];
  const [editing, setEditing] = useState<Offer | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);

  const { data: offers = [], isLoading } = useQuery({ queryKey, queryFn: listOffers });
  const { data: fieldDefinitions = [] } = useFieldDefinitions("offer");

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ defaultValues: DEFAULT_VALUES });

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
    setJsonError(null);
  }

  const createMutation = useMutation({
    mutationFn: createOffer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      closeForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: Parameters<typeof updateOffer>[1] }) =>
      updateOffer(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      closeForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteOffer,
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  function openCreate() {
    setEditing(null);
    reset(DEFAULT_VALUES);
    setFormOpen(true);
  }

  function openEdit(offer: Offer) {
    setEditing(offer);
    reset({
      name: offer.name,
      applies_to_json: JSON.stringify(offer.applies_to ?? {}, null, 2),
      active_from: toDatetimeLocal(offer.active_from),
      active_to: toDatetimeLocal(offer.active_to),
      custom_fields: offer.custom_fields ?? {},
    });
    setFormOpen(true);
  }

  function onSubmit(values: FormValues) {
    let appliesTo: Record<string, unknown>;
    try {
      appliesTo = values.applies_to_json.trim() ? JSON.parse(values.applies_to_json) : {};
    } catch {
      setJsonError("Applies to must be valid JSON, e.g. {\"product_ids\": [\"...\"]}");
      return;
    }
    setJsonError(null);

    const payload = {
      name: values.name,
      applies_to: appliesTo,
      active_from: toIsoOrNull(values.active_from),
      active_to: toIsoOrNull(values.active_to),
      custom_fields: values.custom_fields,
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
          <h1 className="text-2xl font-semibold text-foreground">Offers</h1>
          <p className="text-sm text-muted-foreground">Promotional bundles and campaigns.</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4" />
          New offer
        </Button>
      </div>

      {formOpen && (
        <Card>
          <CardHeader>
            <CardTitle>{editing ? "Edit offer" : "New offer"}</CardTitle>
            <CardDescription>
              {editing ? "Update this offer's details." : "Create a new promotional offer."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="flex flex-col gap-1.5 sm:col-span-2">
                <label htmlFor="name" className="text-sm font-medium">
                  Name
                </label>
                <Input id="name" error={!!errors.name} {...register("name", { required: "Name is required" })} />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="active_from" className="text-sm font-medium">
                  Active from
                </label>
                <Input id="active_from" type="datetime-local" {...register("active_from")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="active_to" className="text-sm font-medium">
                  Active to
                </label>
                <Input id="active_to" type="datetime-local" {...register("active_to")} />
              </div>
              <div className="flex flex-col gap-1.5 sm:col-span-2">
                <label htmlFor="applies_to_json" className="text-sm font-medium">
                  Applies to (JSON)
                </label>
                <textarea
                  id="applies_to_json"
                  rows={4}
                  className="flex w-full rounded-md border border-input bg-card px-3 py-2 font-mono text-xs text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder='{"product_ids": ["..."]}'
                  {...register("applies_to_json")}
                />
                {jsonError && <p className="text-xs text-destructive">{jsonError}</p>}
              </div>

              {fieldDefinitions.length > 0 && (
                <div className="flex flex-col gap-4 border-t border-border pt-4 sm:col-span-2">
                  <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Custom fields</p>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <DynamicCustomFieldsFields definitions={fieldDefinitions} register={register} errors={errors} />
                  </div>
                </div>
              )}

              <div className="flex items-center gap-2 sm:col-span-2">
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving..." : editing ? "Save changes" : "Create offer"}
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
              <TableHead>Active window</TableHead>
              <DynamicCustomFieldsColumns definitions={fieldDefinitions} />
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={3 + fieldDefinitions.length} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && offers.length === 0 && (
              <TableRow>
                <TableCell colSpan={3 + fieldDefinitions.length} className="text-center text-muted-foreground">
                  No offers yet.
                </TableCell>
              </TableRow>
            )}
            {offers.map((offer) => (
              <TableRow key={offer.id}>
                <TableCell className="font-medium text-foreground">{offer.name}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {offer.active_from ? new Date(offer.active_from).toLocaleDateString() : "—"} to{" "}
                  {offer.active_to ? new Date(offer.active_to).toLocaleDateString() : "—"}
                </TableCell>
                <DynamicCustomFieldsCells definitions={fieldDefinitions} values={offer.custom_fields} />
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(offer)} aria-label="Edit">
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => deleteMutation.mutate(offer.id)}
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
