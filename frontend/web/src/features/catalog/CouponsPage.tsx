import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
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
import {
  DynamicCustomFieldsCells,
  DynamicCustomFieldsColumns,
  DynamicCustomFieldsFields,
  useFieldDefinitions,
} from "../custom-fields";
import { ResourceUsageBadge } from "../../components/ResourceUsageBadge";
import { useResourceLimits } from "../../lib/useResourceLimits";
import { createCoupon, deleteCoupon, listCoupons, updateCoupon } from "./api";
import { appliesToSummary, EMPTY_APPLIES_TO, ServiceProductPicker, toAppliesTo, type AppliesTo } from "./ServiceProductPicker";
import type { Coupon, DiscountType } from "./types";

interface FormValues {
  code: string;
  discount_type: DiscountType;
  discount_value: number;
  valid_from: string;
  valid_to: string;
  usage_limit: number | "";
  custom_fields: Record<string, unknown>;
}

const DEFAULT_VALUES: FormValues = {
  code: "",
  discount_type: "percentage",
  discount_value: 0,
  valid_from: "",
  valid_to: "",
  usage_limit: "",
  custom_fields: {},
};

function toDatetimeLocal(iso: string | null): string {
  if (!iso) return "";
  return iso.slice(0, 16);
}

function toIsoOrNull(value: string): string | null {
  return value ? new Date(value).toISOString() : null;
}

export function CouponsPage() {
  const queryClient = useQueryClient();
  const queryKey = ["coupons"];
  const { usage } = useResourceLimits();
  const { atLimit } = usage("coupons");
  const [editing, setEditing] = useState<Coupon | null>(null);
  const [formOpen, setFormOpen] = useState(false);
  const [appliesTo, setAppliesTo] = useState<AppliesTo>(EMPTY_APPLIES_TO);

  const { data: coupons = [], isLoading } = useQuery({ queryKey, queryFn: listCoupons });
  const { data: fieldDefinitions = [] } = useFieldDefinitions("coupon");

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ defaultValues: DEFAULT_VALUES });

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
    setAppliesTo(EMPTY_APPLIES_TO);
  }

  function toPayload(values: FormValues) {
    return {
      code: values.code,
      discount_type: values.discount_type,
      discount_value: values.discount_value,
      applies_to: appliesTo,
      valid_from: toIsoOrNull(values.valid_from),
      valid_to: toIsoOrNull(values.valid_to),
      usage_limit: values.usage_limit === "" ? null : Number(values.usage_limit),
      custom_fields: values.custom_fields,
    };
  }

  const createMutation = useMutation({
    mutationFn: (values: FormValues) => createCoupon(toPayload(values)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      closeForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, values }: { id: string; values: FormValues }) => updateCoupon(id, toPayload(values)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      closeForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deleteCoupon,
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  function openCreate() {
    setEditing(null);
    reset(DEFAULT_VALUES);
    setAppliesTo(EMPTY_APPLIES_TO);
    setFormOpen(true);
  }

  function openEdit(coupon: Coupon) {
    setEditing(coupon);
    reset({
      code: coupon.code,
      discount_type: coupon.discount_type,
      discount_value: Number(coupon.discount_value),
      valid_from: toDatetimeLocal(coupon.valid_from),
      valid_to: toDatetimeLocal(coupon.valid_to),
      usage_limit: coupon.usage_limit ?? "",
      custom_fields: coupon.custom_fields ?? {},
    });
    setAppliesTo(toAppliesTo(coupon.applies_to));
    setFormOpen(true);
  }

  function onSubmit(values: FormValues) {
    if (editing) {
      updateMutation.mutate({ id: editing.id, values });
    } else {
      createMutation.mutate(values);
    }
  }

  const saving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Coupons</h1>
          <p className="text-sm text-muted-foreground">Discount codes your customers can redeem.</p>
        </div>
        <div className="flex items-center gap-2">
          <ResourceUsageBadge resourceKey="coupons" />
          <Button onClick={openCreate} disabled={atLimit} title={atLimit ? "You've reached your plan's limit" : undefined}>
            <Plus className="h-4 w-4" />
            New coupon
          </Button>
        </div>
      </div>

      {formOpen && (
        <Card>
          <CardHeader>
            <CardTitle>{editing ? "Edit coupon" : "New coupon"}</CardTitle>
            <CardDescription>
              {editing ? "Update this coupon's terms." : "Create a new discount code."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="code" className="text-sm font-medium">
                  Code
                </label>
                <Input id="code" error={!!errors.code} {...register("code", { required: "Code is required" })} />
                {errors.code && <p className="text-xs text-destructive">{errors.code.message}</p>}
              </div>
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
              <div className="flex flex-col gap-1.5">
                <label htmlFor="usage_limit" className="text-sm font-medium">
                  Usage limit
                </label>
                <Input id="usage_limit" type="number" min="1" placeholder="Unlimited" {...register("usage_limit")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="valid_from" className="text-sm font-medium">
                  Valid from
                </label>
                <Input id="valid_from" type="datetime-local" {...register("valid_from")} />
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="valid_to" className="text-sm font-medium">
                  Valid to
                </label>
                <Input id="valid_to" type="datetime-local" {...register("valid_to")} />
              </div>

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
                  {saving ? "Saving..." : editing ? "Save changes" : "Create coupon"}
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
              <TableHead>Code</TableHead>
              <TableHead>Discount</TableHead>
              <TableHead>Usage limit</TableHead>
              <TableHead>Valid window</TableHead>
              <TableHead>Applies to</TableHead>
              <DynamicCustomFieldsColumns definitions={fieldDefinitions} />
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={6 + fieldDefinitions.length} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && coupons.length === 0 && (
              <TableRow>
                <TableCell colSpan={6 + fieldDefinitions.length} className="text-center text-muted-foreground">
                  No coupons yet.
                </TableCell>
              </TableRow>
            )}
            {coupons.map((coupon) => (
              <TableRow key={coupon.id}>
                <TableCell className="font-medium text-foreground">
                  <Badge variant="outline">{coupon.code}</Badge>
                </TableCell>
                <TableCell>
                  {coupon.discount_type === "percentage" ? `${coupon.discount_value}%` : coupon.discount_value}
                </TableCell>
                <TableCell>{coupon.usage_limit ?? <span className="text-muted-foreground">Unlimited</span>}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {coupon.valid_from ? new Date(coupon.valid_from).toLocaleDateString() : "—"} to{" "}
                  {coupon.valid_to ? new Date(coupon.valid_to).toLocaleDateString() : "—"}
                </TableCell>
                <TableCell>
                  <span className="text-xs text-muted-foreground">{appliesToSummary(coupon.applies_to)}</span>
                </TableCell>
                <DynamicCustomFieldsCells definitions={fieldDefinitions} values={coupon.custom_fields} />
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(coupon)} aria-label="Edit">
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => deleteMutation.mutate(coupon.id)}
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
