/** Mirrors `fusionflow.modules.workflows.schemas` / `engine.registry` /
 * `engine.graph` on the backend. */

export type WorkflowStatus = "draft" | "published" | "archived";
export type ValidationStatus = "valid" | "invalid";
export type RunStatus = "running" | "completed" | "failed" | "cancelled";
export type StepStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";
export type NodeKind = "trigger" | "action" | "condition";
export type IssueSeverity = "error" | "warning";

export interface Workflow {
  id: string;
  name: string;
  status: WorkflowStatus;
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

/** JSON Schema (subset), as produced by `pydantic.BaseModel.model_json_schema()`. */
export interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, JsonSchemaProperty>;
  required?: string[];
}

export interface JsonSchemaProperty {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  minLength?: number;
  maxLength?: number;
  anyOf?: Array<{ type?: string }>;
}

export interface NodeType {
  node_type: string;
  kind: NodeKind;
  category: string;
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
