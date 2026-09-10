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
import { createProductService, deleteProductService, listProductsServices, updateProductService } from "./api";
import type { ProductService, ProductServiceType } from "./types";

interface ProductServiceCatalogPageProps {
  entityType: ProductServiceType;
  title: string;
  description: string;
  itemNoun: string;
}

interface FormValues {
  name: string;
  description: string;
  base_price: number;
  is_active: boolean;
  custom_fields: Record<string, unknown>;
}

const DEFAULT_VALUES: FormValues = {
  name: "",
  description: "",
  base_price: 0,
  is_active: true,
  custom_fields: {},
};

/**
 * Shared list+form page for `/products` and `/services` — the two routers
 * are separate REST resources on the backend but share one table and one
 * shape, so the frontend mirrors that with one generic component
 * parameterized by `entityType` (see `ProductsPage.tsx`/`ServicesPage.tsx`).
 */
export function ProductServiceCatalogPage({
  entityType,
  title,
  description,
  itemNoun,
}: ProductServiceCatalogPageProps) {
  const queryClient = useQueryClient();
  const queryKey = ["products-services", entityType];
  const [editing, setEditing] = useState<ProductService | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const { data: items = [], isLoading } = useQuery({
    queryKey,
    queryFn: () => listProductsServices(entityType),
  });

  // Fetched dynamically so custom fields render whatever the tenant has
  // configured for this entity_type right now — no hardcoded shape.
  const { data: fieldDefinitions = [] } = useFieldDefinitions(entityType);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({ defaultValues: DEFAULT_VALUES });

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
  }

  const createMutation = useMutation({
    mutationFn: (values: FormValues) =>
      createProductService({
        entity_type: entityType,
        name: values.name,
        description: values.description || null,
        base_price: values.base_price,
        is_active: values.is_active,
        custom_fields: values.custom_fields,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      closeForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, values }: { id: string; values: FormValues }) =>
      updateProductService(entityType, id, {
        name: values.name,
        description: values.description || null,
        base_price: values.base_price,
        is_active: values.is_active,
        custom_fields: values.custom_fields,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      closeForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteProductService(entityType, id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  function openCreate() {
    setEditing(null);
    reset(DEFAULT_VALUES);
    setFormOpen(true);
  }

  function openEdit(item: ProductService) {
    setEditing(item);
    reset({
      name: item.name,
      description: item.description ?? "",
      base_price: Number(item.base_price),
      is_active: item.is_active,
      custom_fields: item.custom_fields ?? {},
    });
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
          <h1 className="text-2xl font-semibold text-foreground">{title}</h1>
          <p className="text-sm text-muted-foreground">{description}</p>
        </div>
        <Button onClick={openCreate}>
          <Plus className="h-4 w-4" />
          New {itemNoun}
        </Button>
      </div>

      {formOpen && (
        <Card>
          <CardHeader>
            <CardTitle>{editing ? `Edit ${itemNoun}` : `New ${itemNoun}`}</CardTitle>
            <CardDescription>
              {editing ? `Update this ${itemNoun}'s details.` : `Add a new ${itemNoun} to your catalog.`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="name" className="text-sm font-medium">
                  Name
                </label>
                <Input id="name" error={!!errors.name} {...register("name", { required: "Name is required" })} />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="base_price" className="text-sm font-medium">
                  Base price
                </label>
                <Input
                  id="base_price"
                  type="number"
                  step="0.01"
                  min="0"
                  {...register("base_price", { valueAsNumber: true })}
                />
              </div>
              <div className="flex flex-col gap-1.5 sm:col-span-2">
                <label htmlFor="description" className="text-sm font-medium">
                  Description
                </label>
                <Input id="description" {...register("description")} />
              </div>
              <div className="flex items-center gap-2">
                <input
                  id="is_active"
                  type="checkbox"
                  className="h-4 w-4 rounded border-input"
                  {...register("is_active")}
                />
                <label htmlFor="is_active" className="text-sm font-medium">
                  Active
                </label>
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
                  {saving ? "Saving..." : editing ? "Save changes" : `Create ${itemNoun}`}
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
              <TableHead>Price</TableHead>
              <TableHead>Status</TableHead>
              <DynamicCustomFieldsColumns definitions={fieldDefinitions} />
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={4 + fieldDefinitions.length} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {!isLoading && items.length === 0 && (
              <TableRow>
                <TableCell colSpan={4 + fieldDefinitions.length} className="text-center text-muted-foreground">
                  No {itemNoun}s yet.
                </TableCell>
              </TableRow>
            )}
            {items.map((item) => (
              <TableRow key={item.id}>
                <TableCell className="font-medium text-foreground">
                  {item.name}
                  {item.description && <p className="text-xs text-muted-foreground">{item.description}</p>}
                </TableCell>
                <TableCell>{item.base_price}</TableCell>
                <TableCell>
                  <Badge variant={item.is_active ? "success" : "outline"}>
                    {item.is_active ? "Active" : "Inactive"}
                  </Badge>
                </TableCell>
                <DynamicCustomFieldsCells definitions={fieldDefinitions} values={item.custom_fields} />
                <TableCell className="text-right">
                  <div className="flex justify-end gap-2">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(item)} aria-label="Edit">
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => deleteMutation.mutate(item.id)}
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
