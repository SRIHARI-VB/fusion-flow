import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { Pencil, Plus } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
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
import { Modal } from "../../components/Modal";
import {
  createBusinessTemplate,
  fetchBusinessTemplates,
  fetchConnectorTypeCatalog,
  fetchPlans,
  updateBusinessTemplate,
  type BusinessTemplateInput,
} from "../../lib/endpoints";
import type { BusinessTemplate } from "../../lib/admin-types";

/**
 * `/templates` — CRUD for `BusinessTemplate`, the "starter kit" a tenant
 * picks during onboarding: a bundle of connector types (granted the moment
 * it's applied) plus an optional default plan.
 *
 * Deliberately not the older, narrower per-entity-type `FieldTemplate`
 * concept (that admin view has been dropped from this page - see this
 * task's report for why) - `FieldTemplate`'s own read-only listing is
 * still served by the backend at `GET /api/admin/templates` for any
 * non-UI consumer, it's just no longer surfaced here.
 */
const EMPTY_FORM: BusinessTemplateInput = {
  key: "",
  name: "",
  description: "",
  vertical: "",
  plan_id: null,
  is_active: true,
  connector_type_ids: [],
};

export function TemplatesPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<BusinessTemplateInput>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: templates, isLoading, isError } = useQuery({
    queryKey: ["admin", "business-templates"],
    queryFn: fetchBusinessTemplates,
  });
  const { data: plans } = useQuery({ queryKey: ["admin", "plans"], queryFn: fetchPlans });
  const { data: connectorTypes } = useQuery({
    queryKey: ["admin", "connector-types"],
    queryFn: fetchConnectorTypeCatalog,
  });

  const createMutation = useMutation({
    mutationFn: () => createBusinessTemplate(form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "business-templates"] });
      closeModal();
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setFormError(axiosErr.response?.data?.detail ?? "Failed to create template.");
    },
  });

  const updateMutation = useMutation({
    mutationFn: () => updateBusinessTemplate(editingId as string, form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "business-templates"] });
      closeModal();
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setFormError(axiosErr.response?.data?.detail ?? "Failed to update template.");
    },
  });

  function openCreateModal() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  }

  function openEditModal(template: BusinessTemplate) {
    setEditingId(template.id);
    setForm({
      key: template.key,
      name: template.name,
      description: template.description ?? "",
      vertical: template.vertical ?? "",
      plan_id: template.plan_id,
      is_active: template.is_active,
      connector_type_ids: template.connector_type_ids,
    });
    setFormError(null);
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditingId(null);
    setFormError(null);
  }

  function toggleConnectorType(id: string) {
    setForm((f) => ({
      ...f,
      connector_type_ids: f.connector_type_ids.includes(id)
        ? f.connector_type_ids.filter((x) => x !== id)
        : [...f.connector_type_ids, id],
    }));
  }

  const planNameById = new Map((plans ?? []).map((p) => [p.id, p.name]));

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Business templates</h1>
          <p className="text-sm text-muted-foreground">
            Starter kits tenants pick during onboarding - a connector bundle plus an optional default plan.
          </p>
        </div>
        <Button onClick={openCreateModal}>
          <Plus className="h-4 w-4" />
          New template
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Templates</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>}
          {isError && (
            <p className="py-8 text-center text-sm text-destructive">Could not load business templates.</p>
          )}
          {!isLoading && !isError && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Vertical</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead>Connectors</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-16" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(templates ?? []).map((tpl) => (
                  <TableRow key={tpl.id}>
                    <TableCell className="font-medium text-foreground">{tpl.name}</TableCell>
                    <TableCell className="text-muted-foreground">{tpl.vertical ?? "—"}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {tpl.plan_id ? planNameById.get(tpl.plan_id) ?? tpl.plan_id : "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{tpl.connector_type_ids.length}</TableCell>
                    <TableCell>
                      <Badge variant={tpl.is_active ? "success" : "secondary"}>
                        {tpl.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Button variant="ghost" size="sm" onClick={() => openEditModal(tpl)}>
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {(templates ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                      No business templates yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Modal
        open={modalOpen}
        onClose={closeModal}
        title={editingId ? "Edit business template" : "New business template"}
        description="Key is immutable once created."
      >
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (editingId) updateMutation.mutate();
            else createMutation.mutate();
          }}
        >
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="tpl-key">
              Key
            </label>
            <Input
              id="tpl-key"
              placeholder="e.g. retail-starter"
              value={form.key}
              disabled={!!editingId}
              onChange={(e) => setForm((f) => ({ ...f, key: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="tpl-name">
              Name
            </label>
            <Input
              id="tpl-name"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="tpl-description">
              Description
            </label>
            <Input
              id="tpl-description"
              value={form.description ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="tpl-vertical">
              Vertical
            </label>
            <Input
              id="tpl-vertical"
              placeholder="e.g. retail"
              value={form.vertical ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, vertical: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="tpl-plan">
              Default plan
            </label>
            <select
              id="tpl-plan"
              className="h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground"
              value={form.plan_id ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, plan_id: e.target.value || null }))}
            >
              <option value="">No default plan</option>
              {(plans ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Connector bundle</span>
            <div className="flex flex-col gap-2 rounded-md border border-border p-2">
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Integrations
                </p>
                <div className="flex max-h-32 flex-col gap-1 overflow-y-auto">
                  {(connectorTypes ?? [])
                    .filter((ct) => ct.category !== "feature")
                    .map((ct) => (
                      <label key={ct.id} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={form.connector_type_ids.includes(ct.id)}
                          onChange={() => toggleConnectorType(ct.id)}
                        />
                        {ct.display_name}
                        <span className="text-xs text-muted-foreground">({ct.key})</span>
                      </label>
                    ))}
                </div>
              </div>
              <div>
                <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  Modules
                </p>
                <div className="flex max-h-32 flex-col gap-1 overflow-y-auto">
                  {(connectorTypes ?? [])
                    .filter((ct) => ct.category === "feature")
                    .map((ct) => (
                      <label key={ct.id} className="flex items-center gap-2 text-sm">
                        <input
                          type="checkbox"
                          checked={form.connector_type_ids.includes(ct.id)}
                          onChange={() => toggleConnectorType(ct.id)}
                        />
                        {ct.display_name}
                        <span className="text-xs text-muted-foreground">({ct.key})</span>
                      </label>
                    ))}
                </div>
              </div>
              {(connectorTypes ?? []).length === 0 && (
                <p className="py-2 text-center text-xs text-muted-foreground">No connector types in the catalog yet.</p>
              )}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            Active (visible to tenants during onboarding)
          </label>
          {formError && <p className="text-sm text-destructive">{formError}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={closeModal}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending || updateMutation.isPending}>
              {editingId ? "Save changes" : "Create"}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
