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
import { ResourceUsageBadge } from "../../components/ResourceUsageBadge";
import { useResourceLimits } from "../../lib/useResourceLimits";
import { createOffer, deleteOffer, listOffers, updateOffer } from "./api";
import { appliesToSummary, EMPTY_APPLIES_TO, ServiceProductPicker, toAppliesTo, type AppliesTo } from "./ServiceProductPicker";
import type { DiscountType, Offer } from "./types";

interface FormValues {
  name: string;
  has_discount: boolean;
  discount_type: DiscountType;
  discount_value: number | "";
  active_from: string;
  active_to: string;
  custom_fields: Record<string, unknown>;
}

const DEFAULT_VALUES: FormValues = {
  name: "",
  has_discount: false,
  discount_type: "percentage",
  discount_value: "",
  active_from: "",
  active_to: "",
  custom_fields: {},
};

function formatDiscount(discountType: DiscountType | null, discountValue: string | null): string {
  if (discountType == null || discountValue == null) return "—";
  return discountType === "percentage" ? `${discountValue}%` : discountValue;
}

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
  const { usage } = useResourceLimits();
  const { atLimit } = usage("offers");
  const [editing, setEditing] = useState<Offer | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [appliesTo, setAppliesTo] = useState<AppliesTo>(EMPTY_APPLIES_TO);

  const { data: offers = [], isLoading } = useQuery({ queryKey, queryFn: listOffers });
  const { data: fieldDefinitions = [] } = useFieldDefinitions("offer");

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<FormValues>({ defaultValues: DEFAULT_VALUES });
  const hasDiscount = watch("has_discount");

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
    setAppliesTo(EMPTY_APPLIES_TO);
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
    setAppliesTo(EMPTY_APPLIES_TO);
    setFormOpen(true);
  }

  function openEdit(offer: Offer) {
    setEditing(offer);
    reset({
      name: offer.name,
      has_discount: offer.discount_type != null,
      discount_type: offer.discount_type ?? "percentage",
      discount_value: offer.discount_value != null ? Number(offer.discount_value) : "",
      active_from: toDatetimeLocal(offer.active_from),
      active_to: toDatetimeLocal(offer.active_to),
      custom_fields: offer.custom_fields ?? {},
    });
    setAppliesTo(toAppliesTo(offer.applies_to));
    setFormOpen(true);
  }

  function onSubmit(values: FormValues) {
    const payload = {
      name: values.name,
      discount_type: values.has_discount ? values.discount_type : null,
      discount_value: values.has_discount && values.discount_value !== "" ? Number(values.discount_value) : null,
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
        <div className="flex items-center gap-2">
          <ResourceUsageBadge resourceKey="offers" />
          <Button onClick={openCreate} disabled={atLimit} title={atLimit ? "You've reached your plan's limit" : undefined}>
            <Plus className="h-4 w-4" />
            New offer
          </Button>
        </div>
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
              <div className="flex items-center gap-2 sm:col-span-2">
                <input id="has_discount" type="checkbox" className="h-4 w-4" {...register("has_discount")} />
                <label htmlFor="has_discount" className="text-sm font-medium">
                  This offer has a specific discount amount
                </label>
              </div>
              {hasDiscount && (
                <>
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="discount_type" className="text-sm font-medium">
                      Discount type
                    </label>
                    <select
                      id="discount_type"
                      className="flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                      {...register("discount_type")}
                    >
                      <option value="percentage">Percentage</option>
                      <option value="fixed_amount">Fixed amount</option>
                    </select>
                  </div>
                  <div className="flex flex-col gap-1.5">
                    <label htmlFor="discount_value" className="text-sm font-medium">
                      Discount value
                    </label>
                    <Input
                      id="discount_value"
                      type="number"
                      step="0.01"
                      min="0"
                      {...register("discount_value", { valueAsNumber: true })}
                    />
                  </div>
                </>
              )}
              <div className="flex flex-col gap-1.5 sm:col-span-2">
                <p className="text-sm font-medium">Applies to</p>
                <p className="text-xs text-muted-foreground">Leave everything unchecked to apply to all services and products.</p>
                <ServiceProductPicker value={appliesTo} onChange={setAppliesTo} />
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
              <TableHead>Discount</TableHead>
              <TableHead>Active window</TableHead>
              <TableHead>Applies to</TableHead>
              <DynamicCustomFieldsColumns definitions={fieldDefinitions} />
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={5 + fieldDefinitions.length} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && offers.length === 0 && (
              <TableRow>
                <TableCell colSpan={5 + fieldDefinitions.length} className="text-center text-muted-foreground">
                  No offers yet.
                </TableCell>
              </TableRow>
            )}
            {offers.map((offer) => (
              <TableRow key={offer.id}>
                <TableCell className="font-medium text-foreground">{offer.name}</TableCell>
                <TableCell className="text-sm text-foreground">
                  {formatDiscount(offer.discount_type, offer.discount_value)}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {offer.active_from ? new Date(offer.active_from).toLocaleDateString() : "—"} to{" "}
                  {offer.active_to ? new Date(offer.active_to).toLocaleDateString() : "—"}
                </TableCell>
                <TableCell>
                  <span className="text-xs text-muted-foreground">{appliesToSummary(offer.applies_to)}</span>
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
