import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { Pencil, Plus, Trash2 } from "lucide-react";
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
  createWorkflowNodeTemplate,
  deleteWorkflowNodeTemplate,
  fetchAdminNodeTypes,
  fetchWorkflowNodeTemplates,
  updateWorkflowNodeTemplate,
  type WorkflowNodeTemplateInput,
} from "../../lib/endpoints";
import type { AdminNodeTypeSummary, WorkflowNodeTemplate } from "../../lib/admin-types";

/**
 * `/workflow-node-templates` — CRUD for `WorkflowNodeTemplate`, the "new
 * integration without a deploy" layer on top of the workflow engine's
 * generic executors. A template is just an admin-friendly palette entry
 * (label/icon/category/default config) over one of these base node types
 * - adding a new WhatsApp capability, third-party API, etc. is data entry
 * here once the underlying adapter/executor exists, not a deploy.
 *
 * `default_config` is edited as raw JSON (a plain textarea) rather than a
 * dynamic schema-driven form: the tenant-facing NodeConfigDrawer already
 * does dynamic-schema rendering for *using* a node inside a workflow, but
 * this page is for *defining* the template's own default values, which
 * differs per `base_node_type` in a way that isn't worth a second
 * schema-rendering implementation for this admin-only, infrequently-used
 * screen.
 */

// Groups a live `GET /api/admin/node-types` result by category for the
// base_node_type <select> below - was previously a hand-maintained list of
// only 4 entries that had already drifted from reality (missing
// module.list/get/create/update, which the real seed scripts use as a
// base_node_type today) since nothing kept it in sync with the engine's
// actual registry. Sourcing it live means it can never go stale again.
function groupByCategory(nodeTypes: AdminNodeTypeSummary[]): [string, AdminNodeTypeSummary[]][] {
  const byCategory = new Map<string, AdminNodeTypeSummary[]>();
  for (const nt of nodeTypes) {
    const list = byCategory.get(nt.category) ?? [];
    list.push(nt);
    byCategory.set(nt.category, list);
  }
  return [...byCategory.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([category, items]) => [category, [...items].sort((a, b) => a.label.localeCompare(b.label))]);
}

interface FormState {
  key: string;
  label: string;
  description: string;
  category: string;
  base_node_type: string;
  icon: string;
  default_config_json: string;
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  key: "",
  label: "",
  description: "",
  category: "Integrations",
  base_node_type: "",
  icon: "",
  default_config_json: "{}",
  is_active: true,
};

export function WorkflowNodeTemplatesPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);

  const { data: templates, isLoading, isError } = useQuery({
    queryKey: ["admin", "workflow-node-templates"],
    queryFn: fetchWorkflowNodeTemplates,
  });

  const { data: nodeTypes = [], isLoading: nodeTypesLoading } = useQuery({
    queryKey: ["admin", "node-types"],
    queryFn: fetchAdminNodeTypes,
  });
  const nodeTypeGroups = groupByCategory(nodeTypes);
  // While editing an existing template, its own base_node_type must always
  // render as a real, selected option even before the live list has
  // loaded (or on the off chance it's since been deregistered) - a
  // disabled select showing nothing would look like data loss, not a
  // permissions/loading state.
  const knownNodeTypeValues = new Set(nodeTypes.map((nt) => nt.node_type));
  const currentValueIsUnlisted = !!form.base_node_type && !knownNodeTypeValues.has(form.base_node_type);

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "workflow-node-templates"] });
  }

  const createMutation = useMutation({
    mutationFn: (payload: WorkflowNodeTemplateInput) => createWorkflowNodeTemplate(payload),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setFormError(axiosErr.response?.data?.detail ?? "Failed to create template.");
    },
  });

  const updateMutation = useMutation({
    mutationFn: (payload: Partial<WorkflowNodeTemplateInput>) =>
      updateWorkflowNodeTemplate(editingId as string, payload),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setFormError(axiosErr.response?.data?.detail ?? "Failed to update template.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (templateId: string) => deleteWorkflowNodeTemplate(templateId),
    onSuccess: invalidate,
  });

  function openCreateModal() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setModalOpen(true);
  }

  function openEditModal(template: WorkflowNodeTemplate) {
    setEditingId(template.id);
    setForm({
      key: template.key,
      label: template.label,
      description: template.description ?? "",
      category: template.category,
      base_node_type: template.base_node_type,
      icon: template.icon ?? "",
      default_config_json: JSON.stringify(template.default_config ?? {}, null, 2),
      is_active: template.is_active,
    });
    setFormError(null);
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditingId(null);
    setFormError(null);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    let defaultConfig: Record<string, unknown>;
    try {
      defaultConfig = JSON.parse(form.default_config_json || "{}");
    } catch {
      setFormError("Default config must be valid JSON.");
      return;
    }
    setFormError(null);

    if (editingId) {
      updateMutation.mutate({
        label: form.label,
        description: form.description || null,
        category: form.category,
        icon: form.icon || null,
        default_config: defaultConfig,
        is_active: form.is_active,
      });
    } else {
      createMutation.mutate({
        key: form.key,
        label: form.label,
        description: form.description || null,
        category: form.category,
        base_node_type: form.base_node_type,
        icon: form.icon || null,
        default_config: defaultConfig,
        is_active: form.is_active,
      });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Workflow node templates</h1>
          <p className="text-sm text-muted-foreground">
            Admin-managed palette entries over the workflow engine's generic executors - add a new
            integration capability to the builder without a deploy.
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
            <p className="py-8 text-center text-sm text-destructive">
              Could not load workflow node templates.
            </p>
          )}
          {!isLoading && !isError && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Label</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Base node type</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-24" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(templates ?? []).map((tpl) => (
                  <TableRow key={tpl.id}>
                    <TableCell className="font-medium text-foreground">{tpl.label}</TableCell>
                    <TableCell className="text-muted-foreground">{tpl.category}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">
                      {tpl.base_node_type}
                    </TableCell>
                    <TableCell>
                      <Badge variant={tpl.is_active ? "success" : "secondary"}>
                        {tpl.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="sm" onClick={() => openEditModal(tpl)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (confirm(`Delete template "${tpl.label}"? This cannot be undone.`)) {
                              deleteMutation.mutate(tpl.id);
                            }
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {(templates ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                      No workflow node templates yet.
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
        title={editingId ? "Edit workflow node template" : "New workflow node template"}
        description="Key and base node type are immutable once created."
      >
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wnt-key">
              Key
            </label>
            <Input
              id="wnt-key"
              placeholder="e.g. send_whatsapp_template_message"
              value={form.key}
              disabled={!!editingId}
              onChange={(e) => setForm((f) => ({ ...f, key: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wnt-label">
              Label
            </label>
            <Input
              id="wnt-label"
              placeholder="e.g. Send WhatsApp Template Message"
              value={form.label}
              onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wnt-description">
              Description
            </label>
            <Input
              id="wnt-description"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wnt-category">
              Palette category
            </label>
            <Input
              id="wnt-category"
              placeholder="e.g. Messaging"
              value={form.category}
              onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wnt-base-type">
              Base node type
            </label>
            <select
              id="wnt-base-type"
              className="h-10 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground disabled:opacity-60"
              value={form.base_node_type}
              disabled={!!editingId}
              required
              onChange={(e) => setForm((f) => ({ ...f, base_node_type: e.target.value }))}
            >
              {!editingId && (
                <option value="" disabled>
                  {nodeTypesLoading ? "Loading node types…" : "Select a node type…"}
                </option>
              )}
              {/* Editing an existing template whose base_node_type isn't (yet, or no
                  longer) in the live list - keep showing its real value instead of a
                  blank/mismatched select. */}
              {currentValueIsUnlisted && <option value={form.base_node_type}>{form.base_node_type}</option>}
              {nodeTypeGroups.map(([category, items]) => (
                <optgroup key={category} label={category}>
                  {items.map((nt) => (
                    <option key={nt.node_type} value={nt.node_type}>
                      {nt.label} ({nt.node_type})
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wnt-default-config">
              Default config (JSON)
            </label>
            <textarea
              id="wnt-default-config"
              className="min-h-32 w-full rounded-md border border-input bg-card p-3 font-mono text-xs text-foreground"
              value={form.default_config_json}
              onChange={(e) => setForm((f) => ({ ...f, default_config_json: e.target.value }))}
              spellCheck={false}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            Active (visible in every tenant's workflow builder palette)
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
