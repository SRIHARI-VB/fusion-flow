import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
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
import { ResourceUsageBadge } from "../../components/ResourceUsageBadge";
import { useResourceLimits } from "../../lib/useResourceLimits";
import { createFieldDefinition, deleteFieldDefinition, updateFieldDefinition } from "./api";
import { useFieldDefinitions } from "./useFieldDefinitions";
import type { CustomFieldEntityType, CustomFieldType, FieldDefinition } from "./types";

const ENTITY_TABS: { value: CustomFieldEntityType; label: string }[] = [
  { value: "product", label: "Products" },
  { value: "service", label: "Services" },
  { value: "coupon", label: "Coupons" },
  { value: "offer", label: "Offers" },
];

const FIELD_TYPES: { value: CustomFieldType; label: string }[] = [
  { value: "text", label: "Text" },
  { value: "number", label: "Number" },
  { value: "boolean", label: "Yes / No" },
  { value: "select", label: "Select (single choice)" },
  { value: "multiselect", label: "Multi-select" },
  { value: "date", label: "Date" },
  { value: "richtext", label: "Rich text" },
];

const NEEDS_OPTIONS: CustomFieldType[] = ["select", "multiselect"];

interface FormValues {
  key: string;
  label: string;
  field_type: CustomFieldType;
  options: string; // comma-separated, only used for select/multiselect
  required: boolean;
  sort_order: number;
}

const DEFAULT_VALUES: FormValues = {
  key: "",
  label: "",
  field_type: "text",
  options: "",
  required: false,
  sort_order: 0,
};

const selectClassName =
  "flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

/**
 * `/settings/custom-fields` — where a business defines its own custom
 * fields for Products/Services/Coupons/Offers, on top of (or instead of)
 * whatever a template seeded during onboarding. Every product/service/
 * coupon/offer create-edit form renders its `custom_fields` inputs
 * dynamically from whatever is defined here (see
 * `DynamicCustomFieldsFields` + `useFieldDefinitions`) — so a field added
 * on this page shows up on the corresponding catalog page immediately,
 * with no code change and no redeploy.
 */
export function CustomFieldsSettingsPage() {
  const queryClient = useQueryClient();
  const { usage } = useResourceLimits();
  // count_field_definitions counts across every entity_type, not just the
  // currently-selected tab - one ceiling for the tenant's whole set.
  const { atLimit } = usage("custom_fields");
  const [entityType, setEntityType] = useState<CustomFieldEntityType>("product");
  const [editing, setEditing] = useState<FieldDefinition | null>(null);
  const [formOpen, setFormOpen] = useState(false);

  const queryKey = ["custom-fields", "definitions", entityType];
  const { data: definitions = [], isLoading } = useFieldDefinitions(entityType);

  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<FormValues>({ defaultValues: DEFAULT_VALUES });

  const fieldType = watch("field_type");

  function openCreateForm() {
    setEditing(null);
    reset(DEFAULT_VALUES);
    setFormOpen(true);
  }

  function openEditForm(definition: FieldDefinition) {
    setEditing(definition);
    reset({
      key: definition.key,
      label: definition.label,
      field_type: definition.field_type,
      options: (definition.options ?? []).join(", "),
      required: definition.required,
      sort_order: definition.sort_order,
    });
    setFormOpen(true);
  }

  function closeForm() {
    setFormOpen(false);
    setEditing(null);
  }

  function toOptionsArray(raw: string): string[] | null {
    const values = raw
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
    return values.length > 0 ? values : null;
  }

  const createMutation = useMutation({
    mutationFn: (values: FormValues) =>
      createFieldDefinition({
        entity_type: entityType,
        key: values.key,
        label: values.label,
        field_type: values.field_type,
        options: NEEDS_OPTIONS.includes(values.field_type) ? toOptionsArray(values.options) : null,
        required: values.required,
        sort_order: values.sort_order,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      closeForm();
    },
  });

  const updateMutation = useMutation({
    mutationFn: (values: FormValues) => {
      if (!editing) throw new Error("No field selected for edit");
      return updateFieldDefinition(editing.id, {
        label: values.label,
        options: NEEDS_OPTIONS.includes(values.field_type) ? toOptionsArray(values.options) : null,
        required: values.required,
        sort_order: values.sort_order,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey });
      closeForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteFieldDefinition(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  function onSubmit(values: FormValues) {
    if (editing) {
      updateMutation.mutate(values);
    } else {
      createMutation.mutate(values);
    }
  }

  const saving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Custom fields</h1>
        <p className="text-sm text-muted-foreground">
          Define the extra fields your business needs on Products, Services, Coupons, and Offers —
          on top of whatever a template applied during onboarding. Fields added here appear on the
          corresponding create/edit form immediately.
        </p>
      </div>

      <div className="flex gap-2 border-b border-border">
        {ENTITY_TABS.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setEntityType(tab.value)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              entityType === tab.value
                ? "border-b-2 border-accent text-accent"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>{ENTITY_TABS.find((t) => t.value === entityType)?.label} fields</CardTitle>
            <CardDescription>Required fields must be filled in on every create/edit form.</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <ResourceUsageBadge resourceKey="custom_fields" />
            <Button onClick={openCreateForm} disabled={atLimit} title={atLimit ? "You've reached your plan's limit" : undefined}>
              <Plus className="mr-2 h-4 w-4" /> Add field
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="text-sm text-muted-foreground">Loading...</p>}
          {!isLoading && definitions.length === 0 && (
            <p className="text-sm text-muted-foreground">
              No custom fields defined yet for {entityType}s. Click "Add field" to create one.
            </p>
          )}
          {!isLoading && definitions.length > 0 && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Key</TableHead>
                  <TableHead>Label</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead>Required</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...definitions]
                  .sort((a, b) => a.sort_order - b.sort_order)
                  .map((definition) => (
                    <TableRow key={definition.id}>
                      <TableCell className="font-mono text-xs">{definition.key}</TableCell>
                      <TableCell>{definition.label}</TableCell>
                      <TableCell>{FIELD_TYPES.find((t) => t.value === definition.field_type)?.label}</TableCell>
                      <TableCell>
                        {definition.required ? <Badge variant="default">Required</Badge> : "—"}
                      </TableCell>
                      <TableCell>
                        {definition.source_template_id ? (
                          <Badge variant="secondary">Template</Badge>
                        ) : (
                          <Badge variant="secondary">Custom</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Button variant="ghost" size="sm" onClick={() => openEditForm(definition)}>
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (confirm(`Delete the "${definition.label}" field? This cannot be undone.`)) {
                              deleteMutation.mutate(definition.id);
                            }
                          }}
                        >
                          <Trash2 className="h-4 w-4 text-destructive" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {formOpen && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>{editing ? `Edit "${editing.label}"` : "Add a new field"}</CardTitle>
            <Button variant="ghost" size="sm" onClick={closeForm}>
              <X className="h-4 w-4" />
            </Button>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-2" onSubmit={handleSubmit(onSubmit)} noValidate>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="key" className="text-sm font-medium">
                  Key
                </label>
                <Input
                  id="key"
                  placeholder="warranty_months"
                  disabled={!!editing}
                  error={!!errors.key}
                  {...register("key", {
                    required: "Key is required",
                    pattern: {
                      value: /^[a-z][a-z0-9_]*$/,
                      message: "Lowercase letters, numbers, and underscores only, starting with a letter",
                    },
                  })}
                />
                {errors.key && <p className="text-xs text-destructive">{errors.key.message}</p>}
                {editing && (
                  <p className="text-xs text-muted-foreground">
                    The key can't be changed after creation — delete and recreate the field instead.
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="label" className="text-sm font-medium">
                  Label
                </label>
                <Input
                  id="label"
                  placeholder="Warranty (months)"
                  error={!!errors.label}
                  {...register("label", { required: "Label is required" })}
                />
                {errors.label && <p className="text-xs text-destructive">{errors.label.message}</p>}
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="field_type" className="text-sm font-medium">
                  Field type
                </label>
                <select id="field_type" className={selectClassName} disabled={!!editing} {...register("field_type")}>
                  {FIELD_TYPES.map((type) => (
                    <option key={type.value} value={type.value}>
                      {type.label}
                    </option>
                  ))}
                </select>
                {editing && (
                  <p className="text-xs text-muted-foreground">
                    The type can't be changed after creation either.
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor="sort_order" className="text-sm font-medium">
                  Sort order
                </label>
                <Input id="sort_order" type="number" {...register("sort_order", { valueAsNumber: true })} />
              </div>

              {NEEDS_OPTIONS.includes(fieldType) && (
                <div className="flex flex-col gap-1.5 sm:col-span-2">
                  <label htmlFor="options" className="text-sm font-medium">
                    Options (comma-separated)
                  </label>
                  <Input id="options" placeholder="Small, Medium, Large" {...register("options")} />
                </div>
              )}

              <div className="flex items-center gap-2 sm:col-span-2">
                <input id="required" type="checkbox" className="h-4 w-4 rounded border-input" {...register("required")} />
                <label htmlFor="required" className="text-sm font-medium">
                  Required on every create/edit form
                </label>
              </div>

              {(createMutation.isError || updateMutation.isError) && (
                <p className="text-sm text-destructive sm:col-span-2">
                  Could not save this field. Check the key is unique for this entity type and try again.
                </p>
              )}

              <div className="flex gap-2 sm:col-span-2">
                <Button type="submit" disabled={saving}>
                  {saving ? "Saving..." : editing ? "Save changes" : "Add field"}
                </Button>
                <Button type="button" variant="ghost" onClick={closeForm}>
                  Cancel
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
