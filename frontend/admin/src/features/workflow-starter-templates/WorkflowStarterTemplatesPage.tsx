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
  createWorkflowStarterTemplate,
  deleteWorkflowStarterTemplate,
  fetchWorkflowStarterTemplates,
  updateWorkflowStarterTemplate,
  validateWorkflowStarterTemplateGraph,
  type WorkflowStarterTemplateInput,
} from "../../lib/endpoints";
import type { GraphValidationResult, WorkflowStarterTemplate } from "../../lib/admin-types";

/** Rule key the backend emits when a template's graph references a
 * placeholder/example connector id - expected for every seeded starter
 * template, since the tenant picks their own connector when they actually
 * use it, so it's rendered as an informational note rather than an error. */
const EXPECTED_CONNECTOR_RULE = "disconnected_connector_reference";

/**
 * `/workflow-starter-templates` — CRUD for `WorkflowStarterTemplate`, a
 * whole authored workflow graph a tenant can start a brand-new workflow
 * from (picked in the "New Workflow" flow's template picker), as opposed
 * to `WorkflowComponent` (a smaller fragment inserted into a workflow
 * already being edited - see the sibling `/workflow-components` page).
 *
 * `graph_json`/`required_object_types` are edited as raw JSON (plain
 * textareas), same convention as `WorkflowNodeTemplatesPage`'s
 * `default_config` field - authoring a real node/edge graph by hand here
 * is an admin-only, infrequent task, not worth a second schema-driven
 * graph editor alongside the tenant-facing canvas.
 */

interface FormState {
  key: string;
  name: string;
  description: string;
  category: string;
  icon: string;
  graph_json_text: string;
  required_object_types_text: string;
  setup_notes: string;
  is_active: boolean;
}

const EMPTY_FORM: FormState = {
  key: "",
  name: "",
  description: "",
  category: "Ecommerce",
  icon: "",
  graph_json_text: '{\n  "nodes": [],\n  "edges": []\n}',
  required_object_types_text: "",
  setup_notes: "",
  is_active: true,
};

export function WorkflowStarterTemplatesPage() {
  const queryClient = useQueryClient();
  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [validationResult, setValidationResult] = useState<GraphValidationResult | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  const { data: templates, isLoading, isError } = useQuery({
    queryKey: ["admin", "workflow-starter-templates"],
    queryFn: fetchWorkflowStarterTemplates,
  });

  function invalidate() {
    queryClient.invalidateQueries({ queryKey: ["admin", "workflow-starter-templates"] });
  }

  const createMutation = useMutation({
    mutationFn: (payload: WorkflowStarterTemplateInput) => createWorkflowStarterTemplate(payload),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setFormError(axiosErr.response?.data?.detail ?? "Failed to create starter template.");
    },
  });

  const updateMutation = useMutation({
    mutationFn: (payload: Partial<Omit<WorkflowStarterTemplateInput, "key">>) =>
      updateWorkflowStarterTemplate(editingId as string, payload),
    onSuccess: () => {
      invalidate();
      closeModal();
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setFormError(axiosErr.response?.data?.detail ?? "Failed to update starter template.");
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (templateId: string) => deleteWorkflowStarterTemplate(templateId),
    onSuccess: invalidate,
  });

  const validateMutation = useMutation({
    mutationFn: (graphJson: Record<string, unknown>) => validateWorkflowStarterTemplateGraph(graphJson),
    onSuccess: (result) => {
      setValidationResult(result);
      setValidationError(null);
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setValidationResult(null);
      setValidationError(axiosErr.response?.data?.detail ?? "Failed to validate graph.");
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

  function openEditModal(template: WorkflowStarterTemplate) {
    setEditingId(template.id);
    setForm({
      key: template.key,
      name: template.name,
      description: template.description ?? "",
      category: template.category,
      icon: template.icon ?? "",
      graph_json_text: JSON.stringify(template.graph_json ?? {}, null, 2),
      required_object_types_text: template.required_object_types
        ? JSON.stringify(template.required_object_types, null, 2)
        : "",
      setup_notes: template.setup_notes ?? "",
      is_active: template.is_active,
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

  function handleGraphJsonChange(value: string) {
    setForm((f) => ({ ...f, graph_json_text: value }));
    setValidationResult(null);
    setValidationError(null);
  }

  function handleValidate() {
    let graphJson: Record<string, unknown>;
    try {
      graphJson = JSON.parse(form.graph_json_text || "{}");
    } catch {
      setValidationResult(null);
      setValidationError("Graph JSON must be valid JSON.");
      return;
    }
    setValidationError(null);
    validateMutation.mutate(graphJson);
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    let graphJson: Record<string, unknown>;
    try {
      graphJson = JSON.parse(form.graph_json_text || "{}");
    } catch {
      setFormError("Graph JSON must be valid JSON.");
      return;
    }
    let requiredObjectTypes: Record<string, unknown>[] | null = null;
    if (form.required_object_types_text.trim()) {
      try {
        requiredObjectTypes = JSON.parse(form.required_object_types_text);
      } catch {
        setFormError("Required object types must be valid JSON (a list, or left empty).");
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
        graph_json: graphJson,
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
        graph_json: graphJson,
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
          <h1 className="text-2xl font-semibold text-foreground">Workflow starter templates</h1>
          <p className="text-sm text-muted-foreground">
            Whole authored workflow graphs a tenant can start a brand-new workflow from, offered in
            the "New Workflow" template picker.
          </p>
        </div>
        <Button onClick={openCreateModal}>
          <Plus className="h-4 w-4" />
          New starter template
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
              Could not load workflow starter templates.
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
                {(templates ?? []).map((tpl) => (
                  <TableRow key={tpl.id}>
                    <TableCell className="font-medium text-foreground">{tpl.name}</TableCell>
                    <TableCell className="text-muted-foreground">{tpl.category}</TableCell>
                    <TableCell className="font-mono text-xs text-muted-foreground">{tpl.key}</TableCell>
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
                            if (confirm(`Delete starter template "${tpl.name}"? This cannot be undone.`)) {
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
                      No workflow starter templates yet.
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
        title={editingId ? "Edit starter template" : "New starter template"}
        description="Key is immutable once created."
      >
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wst-key">
              Key
            </label>
            <Input
              id="wst-key"
              placeholder="e.g. whatsapp_ordering"
              value={form.key}
              disabled={!!editingId}
              onChange={(e) => setForm((f) => ({ ...f, key: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wst-name">
              Name
            </label>
            <Input
              id="wst-name"
              placeholder="e.g. WhatsApp Guided Ordering"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wst-description">
              Description
            </label>
            <Input
              id="wst-description"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wst-category">
              Category
            </label>
            <Input
              id="wst-category"
              placeholder="e.g. Ecommerce"
              value={form.category}
              onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wst-icon">
              Icon
            </label>
            <Input
              id="wst-icon"
              placeholder="e.g. shopping-cart"
              value={form.icon}
              onChange={(e) => setForm((f) => ({ ...f, icon: e.target.value }))}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wst-graph-json">
              Graph JSON
            </label>
            <textarea
              id="wst-graph-json"
              className="min-h-48 w-full rounded-md border border-input bg-card p-3 font-mono text-xs text-foreground"
              value={form.graph_json_text}
              onChange={(e) => handleGraphJsonChange(e.target.value)}
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
                {validationResult.issues.map((issue, idx) => {
                  const isExpectedConnectorIssue = issue.rule === EXPECTED_CONNECTOR_RULE;
                  const isError = issue.severity === "error" && !isExpectedConnectorIssue;
                  return (
                    <div
                      key={`${issue.rule}-${idx}`}
                      className={
                        isExpectedConnectorIssue
                          ? "text-muted-foreground"
                          : isError
                            ? "text-destructive"
                            : "text-amber-600 dark:text-amber-400"
                      }
                    >
                      <span className="font-mono font-medium">[{issue.rule}/{issue.severity}]</span>{" "}
                      {issue.message}
                      {issue.node_id && <span className="text-muted-foreground"> (node: {issue.node_id})</span>}
                      {isExpectedConnectorIssue && (
                        <span className="italic">
                          {" "}
                          — expected, the tenant will pick their own connector when they use this template.
                        </span>
                      )}
                    </div>
                  );
                })}
                <p className="text-muted-foreground">
                  {validationResult.required_connector_type_keys.length > 0
                    ? `Uses: ${validationResult.required_connector_type_keys.join(", ")}`
                    : "No connector dependencies detected."}
                </p>
              </div>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wst-required-object-types">
              Required object types (JSON list, optional)
            </label>
            <textarea
              id="wst-required-object-types"
              className="min-h-24 w-full rounded-md border border-input bg-card p-3 font-mono text-xs text-foreground"
              placeholder="Leave empty if this template needs no custom object type"
              value={form.required_object_types_text}
              onChange={(e) => setForm((f) => ({ ...f, required_object_types_text: e.target.value }))}
              spellCheck={false}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="wst-setup-notes">
              Setup notes (optional)
            </label>
            <textarea
              id="wst-setup-notes"
              className="min-h-20 w-full rounded-md border border-input bg-card p-3 text-sm text-foreground"
              placeholder="e.g. Populate your product catalog before using this template"
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
            Active (offered in every tenant's "New Workflow" template picker)
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
