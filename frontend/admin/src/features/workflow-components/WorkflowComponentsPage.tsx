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
  createWorkflowComponent,
  deleteWorkflowComponent,
  fetchWorkflowComponents,
  updateWorkflowComponent,
  validateWorkflowComponentGraph,
  type WorkflowComponentInput,
} from "../../lib/endpoints";
import type { GraphValidationResult, WorkflowComponent } from "../../lib/admin-types";

/**
 * `/workflow-components` — CRUD for `WorkflowComponent`, a smaller,
 * insertable node/edge fragment a tenant drops into a workflow they're
 * already editing (as opposed to `WorkflowStarterTemplate`, which seeds a
 * whole new workflow). Mirrors `WorkflowNodeTemplatesPage.tsx`'s exact
 * pattern - `graph_fragment`/`required_object_types` are edited as raw JSON
 * on this admin-only, infrequently-used screen for the same reason
 * `default_config` is there: a dynamic schema-driven form for authoring a
 * fragment isn't worth a second implementation of what `NodeConfigDrawer`
 * already does for *using* a node.
 */

interface FormState {
  key: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  graph_fragment_json: string;
  required_object_types_json: string;
  setup_notes: string;
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  key: "",
  name: "",
  description: "",
  category: "",
  icon: "",
  graph_fragment_json: '{\n  "nodes": [],\n  "edges": []\n}',
  required_object_types_json: "",
  setup_notes: "",
  is_active: true,
};

export function WorkflowComponentsPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [validationResult, setValidationResult] = useState<GraphValidationResult | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const { data: components, isLoading, isError } = useQuery({
    queryKey: ["admin", "workflow-components"],
    queryFn: fetchWorkflowComponents,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "workflow-components"] });
  }

  const createMutation = useMutation({
    mutationFn: (payload: WorkflowComponentInput) => createWorkflowComponent(payload),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setFormError(axiosErr.response?.data?.detail ?? "Failed to create component.");
    },
  });

  const updateMutation = useMutation({
    mutationFn: (payload: Partial<Omit<WorkflowComponentInput, "key">>) =>
      updateWorkflowComponent(editingId as string, payload),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setFormError(axiosErr.response?.data?.detail ?? "Failed to update component.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (componentId: string) => deleteWorkflowComponent(componentId),
    onSuccess: invalidate,
  });

  const validateMutation = useMutation({
    mutationFn: (graphFragment: Record<string, unknown>) => validateWorkflowComponentGraph(graphFragment),
    onSuccess: (result) => {
      setValidationResult(result);
      setValidationError(null);
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setValidationResult(null);
      setValidationError(axiosErr.response?.data?.detail ?? "Failed to validate graph fragment.");
    },
  });

  function openCreateModal() {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setFormError(null);
    setValidationResult(null);
    setValidationError(null);
    setModalOpen(true);
  }

  function openEditModal(component: WorkflowComponent) {
    setEditingId(component.id);
    setForm({
      key: component.key,
      name: component.name,
      description: component.description ?? "",
      category: component.category,
      icon: component.icon ?? "",
      graph_fragment_json: JSON.stringify(component.graph_fragment ?? {}, null, 2),
      required_object_types_json: component.required_object_types
        ? JSON.stringify(component.required_object_types, null, 2)
        : "",
      setup_notes: component.setup_notes ?? "",
      is_active: component.is_active,
    });
    setFormError(null);
    setValidationResult(null);
    setValidationError(null);
    setModalOpen(true);
  }

  function closeModal() {
    setModalOpen(false);
    setEditingId(null);
    setFormError(null);
    setValidationResult(null);
    setValidationError(null);
  }

  function handleGraphFragmentChange(value: string) {
    setForm((f) => ({ ...f, graph_fragment_json: value }));
    setValidationResult(null);
    setValidationError(null);
  }

  function handleValidate() {
    let graphFragment: Record<string, unknown>;
    try {
      graphFragment = JSON.parse(form.graph_fragment_json || "{}");
    } catch {
      setValidationResult(null);
      setValidationError("Graph fragment must be valid JSON.");
      return;
    }
    setValidationError(null);
    validateMutation.mutate(graphFragment);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    let graphFragment: Record<string, unknown>;
    try {
      graphFragment = JSON.parse(form.graph_fragment_json || "{}");
    } catch {
      setFormError("Graph fragment must be valid JSON.");
      return;
    }
    let requiredObjectTypes: Record<string, unknown>[] | null = null;
    if (form.required_object_types_json.trim()) {
      try {
        requiredObjectTypes = JSON.parse(form.required_object_types_json);
      } catch {
        setFormError("Required object types must be valid JSON (or left empty).");
        return;
      }
    }
    setFormError(null);

    if (editingId) {
      updateMutation.mutate({
        name: form.name,
        description: form.description || null,
        category: form.category,
        icon: form.icon || null,
        graph_fragment: graphFragment,
        required_object_types: requiredObjectTypes,
        setup_notes: form.setup_notes || null,
        is_active: form.is_active,
      });
    } else {
      createMutation.mutate({
        key: form.key,
        name: form.name,
        description: form.description || null,
        category: form.category,
        icon: form.icon || null,
        graph_fragment: graphFragment,
        required_object_types: requiredObjectTypes,
        setup_notes: form.setup_notes || null,
        is_active: form.is_active,
      });
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Workflow components</h1>
          <p className="text-sm text-muted-foreground">
            Small, insertable node/edge fragments a tenant can drop into a workflow they're already
            editing - not a whole new workflow (see Starter Templates for that).
          </p>
        </div>
        <Button onClick={openCreateModal}>
          <Plus className="h-4 w-4" />
          New component
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Components</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>}
          {isError && (
            <p className="py-8 text-center text-sm text-destructive">
              Could not load workflow components.
            </p>
          )}
          {!isLoading && !isError && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Category</TableHead>
                  <TableHead>Key</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-24" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(components ?? []).map((component) => (
                  <TableRow key={component.id}>
                    <TableCell className="font-medium text-foreground">{component.name}</TableCell>
                    <TableCell className="text-muted-foreground">{component.category}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{component.key}</TableCell>
                    <TableCell>
                      <Badge variant={component.is_active ? "success" : "secondary"}>
                        {component.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="sm" onClick={() => openEditModal(component)}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            if (confirm(`Delete component "${component.name}"? This cannot be undone.`)) {
                              deleteMutation.mutate(component.id);
                            }
                          }}
                        >
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
                {(components ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={5} className="py-8 text-center text-sm text-muted-foreground">
                      No workflow components yet.
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
        title={editingId ? "Edit workflow component" : "New workflow component"}
        description="Key is immutable once created."
      >
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wc-key">
              Key
            </label>
            <Input
              id="wc-key"
              placeholder="e.g. coupon_code_check"
              value={form.key}
              disabled={!!editingId}
              onChange={(e) => setForm((f) => ({ ...f, key: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wc-name">
              Name
            </label>
            <Input
              id="wc-name"
              placeholder="e.g. Coupon Code Check"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wc-description">
              Description
            </label>
            <Input
              id="wc-description"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wc-category">
              Palette category
            </label>
            <Input
              id="wc-category"
              placeholder="e.g. Ecommerce"
              value={form.category}
              onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wc-icon">
              Icon
            </label>
            <Input
              id="wc-icon"
              placeholder="e.g. ticket-percent"
              value={form.icon}
              onChange={(e) => setForm((f) => ({ ...f, icon: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wc-graph-fragment">
              Graph fragment (JSON)
            </label>
            <textarea
              id="wc-graph-fragment"
              className="min-h-40 w-full rounded-md border border-input bg-card p-3 font-mono text-xs text-foreground"
              value={form.graph_fragment_json}
              onChange={(e) => handleGraphFragmentChange(e.target.value)}
              spellCheck={false}
            />
            <div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleValidate}
                disabled={validateMutation.isPending}
              >
                {validateMutation.isPending ? "Validating…" : "Validate"}
              </Button>
            </div>
            {validationError && <p className="text-sm text-destructive">{validationError}</p>}
            {validationResult && (
              <div className="flex flex-col gap-2 rounded-md border border-border bg-muted/40 p-3 text-xs">
                {validationResult.issues.length === 0 && (
                  <p className="text-success">No issues found.</p>
                )}
                {validationResult.issues.map((issue, idx) => (
                  <div key={`${issue.rule}-${idx}`} className="text-destructive">
                    <span className="font-mono font-medium">[{issue.rule}/{issue.severity}]</span>{" "}
                    {issue.message}
                    {issue.node_id && <span className="text-muted-foreground"> (node: {issue.node_id})</span>}
                  </div>
                ))}
                <p className="text-muted-foreground">
                  {validationResult.required_connector_type_keys.length > 0
                    ? `Uses: ${validationResult.required_connector_type_keys.join(", ")}`
                    : "No connector dependencies detected."}
                </p>
              </div>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wc-required-object-types">
              Required object types (JSON, optional)
            </label>
            <textarea
              id="wc-required-object-types"
              className="min-h-24 w-full rounded-md border border-input bg-card p-3 font-mono text-xs text-foreground"
              placeholder="Leave empty if this component needs no custom object type"
              value={form.required_object_types_json}
              onChange={(e) => setForm((f) => ({ ...f, required_object_types_json: e.target.value }))}
              spellCheck={false}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wc-setup-notes">
              Setup notes (optional)
            </label>
            <textarea
              id="wc-setup-notes"
              className="min-h-20 w-full rounded-md border border-input bg-card p-3 text-sm text-foreground"
              placeholder="e.g. Populate your product catalog before using this component"
              value={form.setup_notes}
              onChange={(e) => setForm((f) => ({ ...f, setup_notes: e.target.value }))}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            Active (visible in every tenant's "Insert Component" picker)
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
