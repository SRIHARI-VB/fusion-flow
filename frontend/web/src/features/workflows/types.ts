/** Mirrors `fusionflow.modules.workflows.schemas` / `engine.registry` /
 * `engine.graph` on the backend. */

export type WorkflowStatus = "draft" | "published" | "archived";
/** Which broad shape of workflow this is (backend `purpose` concept) - an
 * "automation" reacts to one event at a time (WhatsApp message, new order,
 * payment, ...); a "broadcast" sends to many recipients at once, kicked off
 * by `broadcast.scheduled_send`. Drives which triggers the node palette
 * offers (see `WorkflowsListPage.tsx`'s new "purpose" step and the
 * `purpose` param threaded into `listNodeTypes` below). */
export type WorkflowPurpose = "automation" | "broadcast";
export type ValidationStatus = "valid" | "invalid";
export type RunStatus = "running" | "waiting" | "completed" | "failed" | "cancelled";
export type StepStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";
export type NodeKind = "trigger" | "action" | "condition";
export type IssueSeverity = "error" | "warning";

/** `GET /workflows/starter-templates` (composable-builder redesign, Phase
 * 6) - a ready-to-use example workflow a tenant can start a new workflow
 * from (see `StarterTemplatePicker.tsx`). The full graph/required-object-
 * type spec stays server-side; this tenant-facing summary is just enough
 * for a picker card. */
export interface WorkflowStarterTemplate {
  id: string;
  key: string;
  name: string;
  description: string | null;
  category: string;
  icon?: string | null;
  /** Connector types (e.g. "whatsapp", "razorpay") this template's graph
   * actually uses, auto-derived server-side from its node types - shown as
   * an informational hint, never a gate on picking the template. */
  required_connector_type_keys?: string[];
  /** Optional free-text admin guidance for anything else worth setting up
   * before using this template (e.g. "populate your product catalog"). */
  setup_notes?: string | null;
  /** Server-computed from this template's own graph (its root trigger's
   * registered `applicable_purposes`) - see `admin.service.
   * compute_workflow_purpose`. `null`/absent means the template isn't tied
   * to one purpose and should show for either. */
  purpose?: WorkflowPurpose | null;
}

/** `GET /workflows/components` - a small, reusable fragment (a handful of
 * nodes+edges) a tenant inserts into a workflow they're already editing,
 * as opposed to `WorkflowStarterTemplate`'s whole-new-workflow shape.
 * `source` distinguishes the admin-curated catalog from a tenant's own
 * saved selection - both are merged into one list by the backend, same
 * "one merged picker" pattern `ModuleCatalogEntry.source` already uses.
 * Unlike `WorkflowStarterTemplate`, `graph_fragment` IS included here -
 * a component is merged into the canvas client-side (fresh node ids,
 * dropped near the current viewport), so the frontend genuinely needs the
 * raw fragment, not just catalog metadata. */
export interface WorkflowComponent {
  id: string;
  name: string;
  description?: string | null;
  category?: string | null;
  icon?: string | null;
  source: "admin" | "user";
  graph_fragment: WorkflowGraphJson;
  required_object_types?: Record<string, unknown>[] | null;
  /** Connector types this component's fragment actually uses, auto-derived
   * server-side - informational only, never a gate on inserting it. */
  required_connector_type_keys?: string[];
  /** Optional free-text admin guidance for anything else worth setting up
   * before using this component. */
  setup_notes?: string | null;
}

export interface Workflow {
  id: string;
  name: string;
  status: WorkflowStatus;
  purpose: WorkflowPurpose;
  /** Advisory "which channel is this workflow for" tag - a `connector_types.key`
   * (e.g. "whatsapp", "instagram") the New Workflow wizard's "channel" step
   * set, or `null` for "General" (no specific channel) - shown as a colored
   * badge on `WorkflowsListPage.tsx`. Never enforced against the actual
   * graph's trigger node type - purely informational. */
  channel_connector_type_key: string | null;
  current_published_version_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ValidationIssue {
  rule: string;
  severity: IssueSeverity;
  message: string;
  node_id: string | null;
}

/** JSON Schema (subset), as produced by `pydantic.BaseModel.model_json_schema()`.
 * `$defs` holds nested `BaseModel` sub-schemas pydantic factors out and
 * references via `$ref` (e.g. a `list[SomeSubModel]` field's `items`) -
 * see `jsonSchemaForm.ts`'s `resolveRef`/`resolveItemsSchema` for how
 * those get resolved back into an inline shape for form rendering. */
export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
  $defs?: Record<string, JsonSchemaProperty>;
}

/** A property can also stand in for a full nested schema once a `$ref`
 * has been resolved (pydantic's nested-`BaseModel` sub-schemas have
 * exactly the same shape as a top-level `JsonSchema`) - hence this also
 * carries `properties`/`required`/`$ref`/`items`, not just leaf-field
 * attributes. */
export interface JsonSchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  minLength?: number;
  maxLength?: number;
  minItems?: number;
  maxItems?: number;
  anyOf?: Array<{ type?: string }>;
  items?: JsonSchemaProperty;
  $ref?: string;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
  /** Pydantic `json_schema_extra` hint - today only `"textarea"` is
   * recognized (see `jsonSchemaForm.ts`'s `fieldKind`), marking a plain
   * string field as multi-line message/body content rather than a short
   * single-line value. */
  format?: string;
  /** Companion to `format === "auto_ref"` - which upstream output leaf key
   * (e.g. `"recipients"`, `"message_id"`) this field should auto-resolve
   * to a reference for (see `jsonSchemaForm.ts`'s `"auto_ref"` field kind
   * and `NodeInlineForm.tsx`'s render branch for it). */
  ref_suffix?: string;
}

export interface NodeType {
  node_type: string;
  kind: NodeKind;
  category: string;
  /** Optional second grouping level under `category` for the palette
   * (e.g. category="Messages", subcategory="Media"/"Location"/...) -
   * `null`/absent means no subgrouping, rendered flat under `category`. */
  subcategory?: string | null;
  label: string;
  description: string;
  config_schema: JsonSchema;
  output_handles: string[] | null;
  /** Handles that MAY be wired 0 or 1 times (e.g. Try/Catch's "success"/
   * "error") - distinct from `output_handles`' exactly-once-each. */
  optional_output_handles?: string[] | null;
  /** Opt-in embedding (Loop/TryCatch/Parallel) - see
   * `engine.registry.NodeExecutor.can_contain_children`'s docstring. */
  can_contain_children?: boolean;
  child_role?: string | null;
  /** Set only for a `WorkflowNodeTemplate`-backed palette entry - the
   * config a newly dropped node of this type should be pre-filled with. */
  default_config?: Record<string, unknown>;
  /** Present only on a template-backed entry - which real registered
   * node type this one compiles to at publish time. */
  base_node_type?: string | null;
  /** Which connector type (by key) a tenant must be entitled to for this
   * node type to appear at all - `null`/absent means "not tied to one
   * module/connector," never gated. The `/workflows/node-types` response
   * is already filtered server-side to only entitled entries, so the
   * frontend never re-checks this for visibility - it's only read here
   * for the channel filter bar (`ChannelFilterBar.tsx`) and for prefilling
   * a dropped node's `connector_instance_id`. */
  required_connector_type_key?: string | null;
  /** Same JSON-Schema-lite shape as `config_schema`, describing the
   * well-known keys of this node's `Success.output` - `null`/absent for
   * most node types (not every one declares it). Walked by
   * `flattenOutputPaths` to build the "insert variable" picker's options. */
  output_schema?: JsonSchema | null;
  /** Per-config-field precomputed options (already filtered to what the
   * tenant is entitled to/has connected), keyed by config field name - e.g.
   * `{"connector_instance_id": [{value, label}]}`. `null`/absent means no
   * field on this node type has computable suggestions. */
  field_suggestions?: Record<string, { value: string; label: string }[]> | null;
  /** Composable-builder redesign: a `lucide-react` icon key for the
   * palette card (see `nodes/cardSummaries.ts`'s `NODE_ICONS`), and the
   * task-oriented palette bucket this entry shows under by default
   * ("Talk to Customer" / "Records" / "Payments" / "Flow Control" /
   * "Advanced" / "Triggers") - additive, layered above `category`/
   * `subcategory` (still used by `ChannelFilterBar`/`NodePalette`'s
   * secondary grouping), not a replacement for them. Always present
   * (backend fills in a fallback bucket for any node type that doesn't
   * declare one explicitly). */
  icon?: string | null;
  palette_group: string;
}

/** One field a `records.query`/`records.upsert` node's `fields`/`filters`
 * config can target, or one field on a `whatsapp.ask_choice` module
 * source's underlying rows - the same flat shape whether it came from a
 * fixed module's schema or a tenant's own custom object type (see
 * `GET /workflows/modules`, backend `module_catalog.py`). */
export interface ModuleField {
  key: string;
  label: string;
  field_type: string;
  options?: unknown[] | null;
  required: boolean;
}

/** One entry in the unified module picker (`GET /workflows/modules`): a
 * fixed module (Products, Orders, ...) or one of this tenant's own custom
 * object types (Delivery, Appointment, ...) - the same shape either way. */
export interface ModuleCatalogEntry {
  key: string;
  label: string;
  icon?: string | null;
  category: string;
  source: "fixed" | "custom";
  supported_operations: string[];
  fields: ModuleField[];
}

/** One React Flow node's `data` payload — matches the backend's
 * `engine.graph.GraphNodeData` (camelCase `nodeType` alias). */
export interface WorkflowNodeData {
  nodeType: string;
  label?: string;
  config: Record<string, unknown>;
  [key: string]: unknown;
}

export interface WorkflowGraphNode {
  id: string;
  type?: string;
  data: WorkflowNodeData;
  position: { x: number; y: number };
  /** Set only for a node embedded inside a container - matches React
   * Flow v12's own `parentId`/`extent: "parent"` node nesting, so the
   * persisted graph JSON needs no translation layer either direction. */
  parentId?: string | null;
  /** Container dimensions, persisted so a re-opened workflow renders the
   * container at the size the author left it. Leaf nodes never set this. */
  width?: number;
  height?: number;
}

export interface EdgeFilter {
  field_path: string;
  operator: string;
  value: unknown;
}

export interface WorkflowGraphEdgeData {
  filter?: EdgeFilter | null;
  label?: string | null;
  // React Flow's own `Edge.data` type requires `Record<string, unknown>`.
  [key: string]: unknown;
}

export interface WorkflowGraphEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  data?: WorkflowGraphEdgeData | null;
}

export interface WorkflowGraphJson {
  nodes: WorkflowGraphNode[];
  edges: WorkflowGraphEdge[];
}

export interface WorkflowVersion {
  id: string;
  workflow_id: string;
  version_number: number;
  graph: WorkflowGraphJson;
  validation_status: ValidationStatus | null;
  validation_errors: ValidationIssue[] | null;
  published_at: string | null;
  created_by: string | null;
  created_at: string;
}

export interface PublishResponse {
  workflow: Workflow;
  version: WorkflowVersion;
  valid: boolean;
  issues: ValidationIssue[];
}

export interface RunStep {
  id: string;
  node_id: string;
  node_type: string;
  status: StepStatus;
  input: Record<string, unknown> | null;
  output: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
  attempt: number;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  workflow_version_id: string;
  trigger_event_ref: string | null;
  status: RunStatus;
  started_at: string;
  completed_at: string | null;
  loop_guard_count: number;
}

export interface WorkflowRunDetail extends WorkflowRun {
  steps: RunStep[];
}

/** The publish-time validation rules, in a stable display order for the
 * validation panel. `unsafe_loops` already covers the container-aware
 * cycle check (a cycle fully inside one Loop container's body is
 * auto-safe) - that's the same rule id, not a separate entry;
 * `containment_validity` is the one genuinely new rule added for
 * containers (a parentId must reference an actual container type, and no
 * edge may cross a container boundary). */
export const VALIDATION_RULES: Array<{ rule: string; label: string }> = [
  { rule: "missing_required_fields", label: "Required fields" },
  { rule: "disconnected_connector_reference", label: "Connector references" },
  { rule: "unreachable_nodes", label: "Reachability" },
  { rule: "invalid_branches", label: "Branch wiring" },
  { rule: "unsafe_loops", label: "Loop safety" },
  { rule: "containment_validity", label: "Container structure" },
];
