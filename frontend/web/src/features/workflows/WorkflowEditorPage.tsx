import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addEdge,
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type NodeProps,
  type OnNodeDrag,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ArrowLeft, Blocks, Layers, Maximize2, Minimize2, PlayCircle, Save, ShieldCheck, Upload } from "lucide-react";
import { Button, Input } from "@fusion-flow/ui";
import { useLayoutStore } from "../../lib/layout-store";
import {
  createComponent,
  getWorkflow,
  listNodeTypes,
  listWorkflowVersions,
  provisionComponent,
  publishWorkflow,
  simulateWorkflow,
  updateWorkflow,
} from "./api";
import type {
  NodeType,
  ValidationIssue,
  WorkflowComponent,
  WorkflowGraphEdge,
  WorkflowGraphEdgeData,
  WorkflowGraphJson,
  WorkflowGraphNode,
  WorkflowRunDetail,
} from "./types";
import { flattenOutputPaths } from "./jsonSchemaForm";
import { CardNode } from "./nodes/CardNode";
import { ContainerNode, CONTAINER_MIN_HEIGHT, CONTAINER_MIN_WIDTH } from "./nodes/ContainerNode";
import { NodePalette } from "./components/NodePalette";
import { NodeConfigDrawer } from "./components/NodeConfigDrawer";
import { EdgeConfigDrawer } from "./components/EdgeConfigDrawer";
import { ValidationPanel } from "./components/ValidationPanel";
import { RunStepTrace } from "./components/RunStepTrace";
import { SaveComponentDialog } from "./components/SaveComponentDialog";
import { ComponentPicker } from "./components/ComponentPicker";
import { useConnectorInstances } from "../connectors/hooks";
import {
  CONTAINER_RF_TYPE,
  enrichNodes,
  edgesFromJson,
  toGraphJson,
  type CardNodeData,
} from "./graphUtils";

/** Remaps a component fragment's node/edge ids to fresh, collision-proof
 * ones (a short random suffix per fragment-insert, not per node — cheap
 * uniqueness without a server round-trip) and offsets every node's
 * position so the fragment's own top-left lands near `targetPosition`
 * (the current viewport's visible center) instead of stacking exactly on
 * top of whatever's already at the graph's origin. Operates on the raw
 * `WorkflowGraphJson` shape (pre-`enrichNodes`), mirroring how a freshly
 * hydrated/dropped node is built elsewhere in this file. */
function remapComponentFragment(
  fragment: WorkflowGraphJson,
  targetPosition: { x: number; y: number },
): WorkflowGraphJson {
  const suffix = `_${Math.random().toString(36).slice(2, 8)}`;
  const idMap = new Map(fragment.nodes.map((n) => [n.id, `${n.id}${suffix}`]));

  const minX = Math.min(...fragment.nodes.map((n) => n.position.x));
  const minY = Math.min(...fragment.nodes.map((n) => n.position.y));
  const offset = { x: targetPosition.x - minX, y: targetPosition.y - minY };

  const nodes: WorkflowGraphNode[] = fragment.nodes.map((n) => ({
    ...n,
    id: idMap.get(n.id) ?? n.id,
    position: { x: n.position.x + offset.x, y: n.position.y + offset.y },
    ...(n.parentId ? { parentId: idMap.get(n.parentId) ?? n.parentId } : {}),
  }));

  const edges: WorkflowGraphEdge[] = fragment.edges.map((e) => ({
    ...e,
    id: `${e.id}${suffix}`,
    source: idMap.get(e.source) ?? e.source,
    target: idMap.get(e.target) ?? e.target,
  }));

  return { nodes, edges };
}

const EMPTY_GRAPH: WorkflowGraphJson = { nodes: [], edges: [] };

// Only these palette categories are actually channel-specific (message
// templates/session sends differ per connected number/account) - every
// other category (Ecommerce, Support, Customers, Data, ...) also carries
// `required_connector_type_key` for entitlement gating, but must stay
// visible regardless of which channel is selected in the filter bar.
const MESSAGING_CATEGORIES = new Set(["Messaging", "Messages"]);

/** Absolute (canvas-space) position for a node that may be nested inside
 * one or more containers — walks `parentId` up to the top level, summing
 * each ancestor's own (already-absolute, since containers are never
 * nested inside another container in this proof-of-concept) position.
 * Used by the drag-into/out-of-container handler to convert between a
 * node's parent-relative `position` (what React Flow stores once
 * `parentId` is set) and absolute canvas coordinates. */
function toAbsolutePosition(
  node: { position: { x: number; y: number }; parentId?: string | null },
  nodesById: Map<string, Node<CardNodeData>>,
): { x: number; y: number } {
  if (!node.parentId) return node.position;
  const parent = nodesById.get(node.parentId);
  if (!parent) return node.position;
  const parentAbsolute = toAbsolutePosition(parent, nodesById);
  return { x: node.position.x + parentAbsolute.x, y: node.position.y + parentAbsolute.y };
}

function findContainerAt(point: { x: number; y: number }, nds: Node<CardNodeData>[]): Node<CardNodeData> | null {
  for (const n of nds) {
    if (n.type !== CONTAINER_RF_TYPE) continue;
    const width = n.width ?? CONTAINER_MIN_WIDTH;
    const height = n.height ?? CONTAINER_MIN_HEIGHT;
    if (point.x >= n.position.x && point.x <= n.position.x + width && point.y >= n.position.y && point.y <= n.position.y + height) {
      return n;
    }
  }
  return null;
}

function WorkflowEditorInner({ workflowId }: { workflowId: string }) {
  const queryClient = useQueryClient();
  const reactFlow = useReactFlow();
  const wrapperRef = useRef<HTMLDivElement>(null);
  const fullView = useLayoutStore((s) => s.fullView);
  const setFullView = useLayoutStore((s) => s.setFullView);

  // Full view is a per-editing-session toggle, not a durable preference -
  // leaving this page (navigating away, or unmounting for any other
  // reason) must never strand the rest of the app chrome-less.
  useEffect(() => {
    return () => setFullView(false);
  }, [setFullView]);

  const { data: workflow } = useQuery({ queryKey: ["workflow", workflowId], queryFn: () => getWorkflow(workflowId) });
  const { data: versions } = useQuery({
    queryKey: ["workflow-versions", workflowId],
    queryFn: () => listWorkflowVersions(workflowId),
  });
  const { data: nodeTypes = [] } = useQuery({ queryKey: ["workflow-node-types"], queryFn: listNodeTypes });
  const { data: connectorInstances = [] } = useConnectorInstances();

  // A raw `connector_instance_id` UUID means nothing to a non-technical
  // reader - `CardNode`'s bespoke summaries (`cardSummaries.ts`) resolve
  // it to the channel's own display name via this lookup. React Flow
  // custom node components only receive their own `NodeProps`, so this is
  // threaded in as a plain closure captured by a `nodeTypes` map wrapper
  // (recomputed only when the instance list changes) rather than
  // denormalized onto every node's `data` - `enrichNodes` already runs
  // once at hydration time and wouldn't otherwise re-run when instances
  // load asynchronously or a node is dropped fresh via `onDrop`.
  const connectorInstanceLabel = useCallback(
    (instanceId: string) => connectorInstances.find((i) => i.id === instanceId)?.display_name,
    [connectorInstances],
  );
  const nodeTypesForFlow = useMemo(() => {
    const cardNodeWithContext = (props: NodeProps<Node<CardNodeData>>) => (
      <CardNode {...props} connectorInstanceLabel={connectorInstanceLabel} />
    );
    return {
      trigger: cardNodeWithContext,
      action: cardNodeWithContext,
      condition: cardNodeWithContext,
      [CONTAINER_RF_TYPE]: ContainerNode,
    };
  }, [connectorInstanceLabel]);

  const nodeTypesByKey = useMemo(() => new Map(nodeTypes.map((nt) => [nt.node_type, nt])), [nodeTypes]);
  const latestVersion = versions?.[0];

  const [name, setName] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<CardNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [selectedChannelInstanceId, setSelectedChannelInstanceId] = useState<string | null>(null);

  // Channel-first filter (Part D): the selected instance narrows only the
  // Messaging-category nodes to its own connector type — `required_connector_type_key`
  // is also set on plenty of non-messaging entries (e.g. "Create Ticket
  // Record" requires "tickets") purely for entitlement gating, and those
  // must stay visible regardless of which channel is selected. Only the
  // channel's own message-template/session-send surface actually differs
  // per channel; generic modules (Support, Ecommerce, Customers, Data, ...)
  // don't.
  const selectedChannelInstance = useMemo(
    () => connectorInstances.find((i) => i.id === selectedChannelInstanceId) ?? null,
    [connectorInstances, selectedChannelInstanceId],
  );
  const paletteNodeTypes = useMemo(() => {
    if (!selectedChannelInstance) return nodeTypes;
    return nodeTypes.filter((t) => {
      if (!MESSAGING_CATEGORIES.has(t.category)) return true;
      return !t.required_connector_type_key || t.required_connector_type_key === selectedChannelInstance.connector_type_key;
    });
  }, [nodeTypes, selectedChannelInstance]);

  const [autosave, setAutosave] = useState(false);
  const [validationIssues, setValidationIssues] = useState<ValidationIssue[] | null>(null);
  const [showValidation, setShowValidation] = useState(false);
  const [showTestPanel, setShowTestPanel] = useState(false);
  const [testPayload, setTestPayload] = useState("{}");
  const [lastRun, setLastRun] = useState<WorkflowRunDetail | null>(null);
  const [showSaveComponentDialog, setShowSaveComponentDialog] = useState(false);
  const [showComponentPicker, setShowComponentPicker] = useState(false);
  const [componentStatusMessage, setComponentStatusMessage] = useState<string | null>(null);

  // React Flow already tracks per-node `.selected` via its own built-in
  // click/shift-click/box-select handling (wired through `onNodesChange`,
  // which this page already passes straight through) — no extra selection
  // UI or state is needed to support "save this selection as a component,"
  // only reading what's already there.
  const selectedNodes = useMemo(() => nodes.filter((n) => n.selected), [nodes]);

  const hydratedRef = useRef(false);

  useEffect(() => {
    if (workflow) setName(workflow.name);
  }, [workflow]);

  // Hydrate the canvas from the latest version exactly once (per workflow
  // load) so an in-progress edit isn't clobbered by a background refetch.
  useEffect(() => {
    if (hydratedRef.current || nodeTypes.length === 0) return;
    const graph = latestVersion?.graph ?? EMPTY_GRAPH;
    setNodes(enrichNodes(graph.nodes, nodeTypesByKey));
    setEdges(edgesFromJson(graph.edges));
    hydratedRef.current = true;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestVersion, nodeTypes]);

  const updateMutation = useMutation({
    mutationFn: (graph: WorkflowGraphJson) => updateWorkflow(workflowId, { name, graph }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["workflow-versions", workflowId] });
      queryClient.invalidateQueries({ queryKey: ["workflow", workflowId] });
    },
  });

  const publishMutation = useMutation({
    mutationFn: () => publishWorkflow(workflowId),
    onSuccess: (result) => {
      setValidationIssues(result.issues);
      setShowValidation(true);
      queryClient.invalidateQueries({ queryKey: ["workflow-versions", workflowId] });
      queryClient.invalidateQueries({ queryKey: ["workflow", workflowId] });
    },
  });

  const simulateMutation = useMutation({
    mutationFn: (payload: Record<string, unknown>) => simulateWorkflow(workflowId, payload),
    onSuccess: (run) => setLastRun(run),
  });

  const saveComponentMutation = useMutation({
    mutationFn: createComponent,
    onSuccess: (component) => {
      setShowSaveComponentDialog(false);
      setComponentStatusMessage(`Saved "${component.name}" as a component.`);
      setTimeout(() => setComponentStatusMessage(null), 4000);
      queryClient.invalidateQueries({ queryKey: ["workflow-components"] });
    },
  });

  function handleSaveComponent(payload: { name: string; description: string | null; category: string | null; icon: string | null }) {
    const selectedIds = new Set(selectedNodes.map((n) => n.id));
    const fragmentGraph = toGraphJson(
      selectedNodes,
      edges.filter((e) => selectedIds.has(e.source) && selectedIds.has(e.target)),
    );
    saveComponentMutation.mutate({ ...payload, graph_fragment: fragmentGraph });
  }

  async function handleInsertComponent(component: WorkflowComponent) {
    // Auto-provisions any custom object type this component's fragment
    // assumes exists (e.g. "Post-Purchase Rating Request" needs a
    // "feedback" object type) before dropping its nodes onto the canvas —
    // same "provision, then instantiate" order `StarterTemplatePicker`'s
    // server-side flow already follows for a whole new workflow.
    await provisionComponent(component.id);

    // Drop the fragment in genuinely empty canvas space - to the right of
    // everything already on the graph, at the same top as the highest
    // existing node - rather than always at the viewport's visible center,
    // which routinely landed right on top of whatever was already there.
    // An empty canvas has nothing to avoid, so it falls back to the old
    // viewport-center placement.
    const margin = 80;
    const targetPosition =
      nodes.length > 0
        ? {
            x: Math.max(...nodes.map((n) => n.position.x + (n.width ?? 260))) + margin,
            y: Math.min(...nodes.map((n) => n.position.y)),
          }
        : (() => {
            const centerScreen = wrapperRef.current?.getBoundingClientRect();
            return centerScreen
              ? reactFlow.screenToFlowPosition({
                  x: centerScreen.left + centerScreen.width / 2,
                  y: centerScreen.top + centerScreen.height / 2,
                })
              : { x: 0, y: 0 };
          })();

    const remapped = remapComponentFragment(component.graph_fragment, targetPosition);
    const insertedNodes = enrichNodes(remapped.nodes, nodeTypesByKey);
    setNodes((nds) => [...nds, ...insertedNodes]);
    setEdges((eds) => [...eds, ...edgesFromJson(remapped.edges)]);
    setShowComponentPicker(false);
    setComponentStatusMessage(`Inserted "${component.name}" — some wiring may still need connecting.`);
    setTimeout(() => setComponentStatusMessage(null), 4000);
    // The fragment may have landed outside the current viewport (it's
    // placed to the right of everything else) - bring it into view instead
    // of leaving the user staring at wherever they already were.
    requestAnimationFrame(() => {
      reactFlow.fitView({ nodes: insertedNodes.map((n) => ({ id: n.id })), padding: 0.3, duration: 300 });
    });
  }

  function handleSave() {
    updateMutation.mutate(toGraphJson(nodes, edges));
  }

  function handlePublish() {
    // Publish always validates the current draft on the backend; saving
    // first means the graph on screen is what gets validated/published.
    updateMutation.mutate(toGraphJson(nodes, edges), {
      onSuccess: () => publishMutation.mutate(),
    });
  }

  function handleRunTest() {
    let parsed: Record<string, unknown> = {};
    try {
      parsed = testPayload.trim() ? JSON.parse(testPayload) : {};
    } catch {
      return;
    }
    simulateMutation.mutate(parsed);
  }

  const onConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: `e_${connection.source}_${connection.sourceHandle ?? "default"}_${connection.target}_${Date.now()}`,
          },
          eds,
        ),
      );
    },
    [setEdges],
  );

  const onDragOver = useCallback((event: React.DragEvent) => {
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
  }, []);

  const onDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      const nodeTypeKey = event.dataTransfer.getData("application/reactflow");
      const nodeType = nodeTypesByKey.get(nodeTypeKey);
      if (!nodeType) return;

      const absolutePosition = reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const id = `node_${Math.random().toString(36).slice(2, 10)}`;
      // A trigger only makes sense as a graph root - never droppable
      // inside a container (client-side guard; the real boundary is
      // publish-time validation's containment-validity rule).
      const container =
        nodeType.kind !== "trigger" ? findContainerAt(absolutePosition, nodes) : null;

      // A channel-scoped drop (Part D): pre-fill the new node's
      // `connector_instance_id` with the currently selected channel, so
      // the field's own dropdown (Part C) just shows up pre-selected.
      const defaultConfig = nodeType.default_config ?? {};
      const config =
        selectedChannelInstance && nodeType.config_schema.properties?.connector_instance_id
          ? { ...defaultConfig, connector_instance_id: selectedChannelInstance.id }
          : defaultConfig;

      const newNode: Node<CardNodeData> = {
        id,
        type: nodeType.can_contain_children ? CONTAINER_RF_TYPE : nodeType.kind,
        position: container
          ? { x: absolutePosition.x - container.position.x, y: absolutePosition.y - container.position.y }
          : absolutePosition,
        data: {
          nodeType: nodeType.node_type,
          label: nodeType.label,
          config,
          __meta: nodeType,
        },
        ...(container ? { parentId: container.id, extent: "parent" as const } : {}),
      };
      setNodes((nds) => [...nds, newNode]);
    },
    [nodeTypesByKey, nodes, reactFlow, setNodes, selectedChannelInstance],
  );

  // Drag-into-container mechanics for an *existing* node: dragging it so
  // its position falls inside a container's bounds sets parentId/extent
  // ("parent") on drop; dragging it back outside clears parentId. Uses
  // simple bounding-box containment against the dragged node's own
  // (already-updated-by-RF) position rather than `getIntersectingNodes`,
  // since the latter's rect-overlap semantics are a worse fit than
  // "does the node's origin point land inside the container" for a card
  // that's usually much smaller than the container it's being dropped
  // into.
  const onNodeDragStop: OnNodeDrag<Node<CardNodeData>> = useCallback(
    (_event, draggedNode) => {
      const meta = nodeTypesByKey.get(draggedNode.data.nodeType as string);
      if (!meta || meta.kind === "trigger" || draggedNode.type === CONTAINER_RF_TYPE) return;

      setNodes((nds) => {
        const nodesById = new Map(nds.map((n) => [n.id, n]));
        const current = nodesById.get(draggedNode.id);
        if (!current) return nds;

        const absolute = toAbsolutePosition({ position: draggedNode.position, parentId: current.parentId }, nodesById);
        const container = findContainerAt(
          absolute,
          nds.filter((n) => n.id !== draggedNode.id),
        );

        return nds.map((n) => {
          if (n.id !== draggedNode.id) return n;

          if (container && container.id !== n.parentId) {
            return {
              ...n,
              parentId: container.id,
              extent: "parent" as const,
              position: { x: absolute.x - container.position.x, y: absolute.y - container.position.y },
            };
          }
          if (!container && n.parentId) {
            const { parentId: _parentId, extent: _extent, ...rest } = n;
            return { ...rest, position: absolute };
          }
          return n;
        });
      });
    },
    [nodeTypesByKey, setNodes],
  );

  function onNodeClick(_event: React.MouseEvent, node: Node) {
    setSelectedNodeId(node.id);
    setSelectedEdgeId(null);
  }

  function onEdgeClick(_event: React.MouseEvent, edge: Edge) {
    setSelectedEdgeId(edge.id);
    setSelectedNodeId(null);
  }

  function onPaneClick() {
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
  }

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) ?? null;
  const selectedNodeType: NodeType | undefined = selectedNode
    ? nodeTypesByKey.get(selectedNode.data.nodeType)
    : undefined;
  const selectedEdge = edges.find((e) => e.id === selectedEdgeId) ?? null;

  // Part B: every node reachable by walking edges backward from the
  // selected node (a plain, honest approximation - no special-casing of
  // container/loop variable scoping) offers its declared `output_schema`
  // leaf paths as "insert variable" suggestions.
  const upstreamSuggestions = useMemo(() => {
    if (!selectedNodeId) return [];
    const ancestorIds = new Set<string>();
    const queue = [selectedNodeId];
    while (queue.length > 0) {
      const current = queue.shift()!;
      for (const edge of edges) {
        if (edge.target === current && !ancestorIds.has(edge.source)) {
          ancestorIds.add(edge.source);
          queue.push(edge.source);
        }
      }
    }
    const suggestions: { path: string; label: string }[] = [];
    for (const ancestorId of ancestorIds) {
      const ancestorNode = nodes.find((n) => n.id === ancestorId);
      if (!ancestorNode) continue;
      const ancestorNodeType = nodeTypesByKey.get(ancestorNode.data.nodeType);
      // `path` (used inside `{{...}}`) must stay the raw graph node id -
      // that's what the backend's templating engine actually resolves
      // against. Only the human-readable breadcrumb `label` prefers the
      // author-set label / node type's own friendly label, same
      // precedence `CardNode.tsx`'s own title computation uses, instead
      // of the opaque `node_abc123` id a non-technical author never typed.
      const friendlyPrefix = ancestorNode.data.label || ancestorNodeType?.label || ancestorNode.data.nodeType;
      for (const { path, label } of flattenOutputPaths(ancestorNodeType?.output_schema, ancestorNode.id)) {
        suggestions.push({ path, label: label.replace(ancestorNode.id, friendlyPrefix) });
      }
    }
    return suggestions;
  }, [selectedNodeId, nodes, edges, nodeTypesByKey]);

  function updateSelectedNodeLabel(label: string) {
    if (!selectedNodeId) return;
    setNodes((nds) => nds.map((n) => (n.id === selectedNodeId ? { ...n, data: { ...n.data, label } } : n)));
  }

  function saveSelectedNodeConfig(config: Record<string, unknown>) {
    if (!selectedNodeId) return;
    setNodes((nds) => nds.map((n) => (n.id === selectedNodeId ? { ...n, data: { ...n.data, config } } : n)));
  }

  function deleteSelectedNode() {
    if (!selectedNodeId) return;
    // Deleting a container also deletes its embedded children - leaving
    // them behind with a dangling parentId would be a malformed graph
    // (publish-time rule 6 would reject it anyway).
    const childIds = new Set(nodes.filter((n) => n.parentId === selectedNodeId).map((n) => n.id));
    const removedIds = new Set([selectedNodeId, ...childIds]);
    setNodes((nds) => nds.filter((n) => !removedIds.has(n.id)));
    setEdges((eds) => eds.filter((e) => !removedIds.has(e.source) && !removedIds.has(e.target)));
    setSelectedNodeId(null);
  }

  // Fired by React Flow's own Backspace/Delete keyboard handling (see the
  // `deleteKeyCode` prop below) for however many nodes were selected -
  // xyflow already removes these nodes and any edges directly connected to
  // them via the standard onNodesChange/onEdgesChange flow (`useNodesState`/
  // `useEdgesState` below already handle that). The one thing it doesn't
  // know about is this app's own container/child nesting convention
  // (`parentId`) - a deleted container's embedded children aren't
  // graph-edge-connected to it, so they'd otherwise survive with a dangling
  // parentId (same cascade `deleteSelectedNode` above already does for a
  // single container deleted via the config drawer's own delete button).
  function handleNodesDelete(deleted: Node<CardNodeData>[]) {
    const deletedIds = new Set(deleted.map((n) => n.id));
    const childIds = nodes.filter((n) => n.parentId && deletedIds.has(n.parentId)).map((n) => n.id);
    if (childIds.length > 0) {
      const childIdSet = new Set(childIds);
      setNodes((nds) => nds.filter((n) => !childIdSet.has(n.id)));
      setEdges((eds) => eds.filter((e) => !childIdSet.has(e.source) && !childIdSet.has(e.target)));
    }
    if (selectedNodeId && deletedIds.has(selectedNodeId)) setSelectedNodeId(null);
  }

  function saveSelectedEdgeData(data: WorkflowGraphEdgeData) {
    if (!selectedEdgeId) return;
    const hasContent = !!data.label || !!data.filter;
    setEdges((eds) =>
      eds.map((e) =>
        e.id === selectedEdgeId ? { ...e, data: hasContent ? data : undefined, label: data.label ?? undefined } : e,
      ),
    );
  }

  return (
    <div
      className={
        fullView
          ? "flex h-screen flex-col overflow-hidden bg-background"
          : "flex h-[calc(100vh-6rem)] flex-col overflow-hidden rounded-lg border border-border bg-background"
      }
    >
      {/* Top bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-4 py-2.5">
        <div className="flex items-center gap-3">
          <Link to="/workflows" className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="h-9 w-56 font-semibold"
            aria-label="Workflow name"
          />
          {workflow && (
            <span className="text-xs text-muted-foreground">
              status: {workflow.status}
              {latestVersion && ` · v${latestVersion.version_number}`}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              className="h-3.5 w-3.5"
              checked={autosave}
              onChange={(e) => setAutosave(e.target.checked)}
            />
            Autosave{autosave ? " (UI only — not wired yet)" : ""}
          </label>

          <Button variant="outline" size="sm" onClick={() => setShowTestPanel((s) => !s)}>
            <PlayCircle className="h-4 w-4" />
            Test
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowValidation((s) => !s)}>
            <ShieldCheck className="h-4 w-4" />
            Validation
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowSaveComponentDialog(true)}
            disabled={selectedNodes.length === 0}
            title={selectedNodes.length === 0 ? "Select one or more nodes on the canvas first" : undefined}
          >
            <Layers className="h-4 w-4" />
            Save as Component
          </Button>
          <Button variant="outline" size="sm" onClick={() => setShowComponentPicker(true)}>
            <Blocks className="h-4 w-4" />
            Insert Component
          </Button>
          <Button variant="outline" size="sm" onClick={handleSave} disabled={updateMutation.isPending}>
            <Save className="h-4 w-4" />
            {updateMutation.isPending ? "Saving..." : "Save"}
          </Button>
          <Button size="sm" onClick={handlePublish} disabled={publishMutation.isPending}>
            <Upload className="h-4 w-4" />
            {publishMutation.isPending ? "Publishing..." : "Publish"}
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setFullView(!fullView)}
            title={fullView ? "Exit full view" : "Full view (hide the app sidebar/topbar)"}
          >
            {fullView ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
            {fullView ? "Exit Full View" : "Full View"}
          </Button>
        </div>
      </div>

      {/* Canvas + palette/drawer */}
      <div className="relative flex flex-1 overflow-hidden">
        <div className="relative flex-1" ref={wrapperRef}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onDrop={onDrop}
            onDragOver={onDragOver}
            onNodeClick={onNodeClick}
            onNodeDragStop={onNodeDragStop}
            onEdgeClick={onEdgeClick}
            onPaneClick={onPaneClick}
            onNodesDelete={handleNodesDelete}
            deleteKeyCode={["Backspace", "Delete"]}
            nodeTypes={nodeTypesForFlow}
            defaultEdgeOptions={{ type: "default", style: { strokeWidth: 2 } }}
            fitView
          >
            <Background />
            <Controls />
            <MiniMap pannable zoomable className="!bg-card" />
          </ReactFlow>

          {showValidation && (
            <ValidationPanel issues={validationIssues} onClose={() => setShowValidation(false)} />
          )}

          {componentStatusMessage && (
            <div className="absolute right-4 top-4 z-20 rounded-md border border-border bg-card px-3 py-2 text-xs text-foreground shadow-lg">
              {componentStatusMessage}
            </div>
          )}

          {showSaveComponentDialog && (
            <SaveComponentDialog
              nodeCount={selectedNodes.length}
              onSave={handleSaveComponent}
              onClose={() => setShowSaveComponentDialog(false)}
              isSaving={saveComponentMutation.isPending}
            />
          )}

          {showComponentPicker && (
            <ComponentPicker onSelect={handleInsertComponent} onClose={() => setShowComponentPicker(false)} />
          )}

          {showTestPanel && (
            <div className="absolute bottom-4 left-4 z-10 w-96 max-h-[60vh] overflow-y-auto rounded-lg border border-border bg-card p-3 shadow-lg">
              <p className="mb-2 text-sm font-semibold text-foreground">Simulate run</p>
              <p className="mb-2 text-xs text-muted-foreground">
                Runs the current graph synchronously using the built-in manual test trigger, bypassing the
                inbox entirely.
              </p>
              <textarea
                className="mb-2 h-24 w-full rounded-md border border-input bg-background p-2 font-mono text-xs"
                value={testPayload}
                onChange={(e) => setTestPayload(e.target.value)}
                placeholder='{"keyword": "refund"}'
              />
              <Button size="sm" onClick={handleRunTest} disabled={simulateMutation.isPending}>
                {simulateMutation.isPending ? "Running..." : "Run test"}
              </Button>
              {simulateMutation.isError && (
                <p className="mt-2 text-xs text-destructive">Simulate failed — check the payload is valid JSON.</p>
              )}
              {lastRun && (
                <div className="mt-3 border-t border-border pt-2">
                  <p className="mb-1 text-xs font-medium text-foreground">Run status: {lastRun.status}</p>
                  <RunStepTrace
                    steps={lastRun.steps}
                    nodeParentMap={new Map(nodes.map((n) => [n.id, n.parentId ?? null]))}
                  />
                </div>
              )}
            </div>
          )}
        </div>

        {selectedNode && selectedNodeType ? (
          <NodeConfigDrawer
            nodeId={selectedNode.id}
            nodeType={selectedNodeType}
            label={selectedNode.data.label ?? ""}
            config={selectedNode.data.config ?? {}}
            onLabelChange={updateSelectedNodeLabel}
            onSave={saveSelectedNodeConfig}
            onClose={() => setSelectedNodeId(null)}
            onDelete={deleteSelectedNode}
            upstreamSuggestions={upstreamSuggestions}
          />
        ) : selectedEdge ? (
          <EdgeConfigDrawer
            edgeId={selectedEdge.id}
            data={selectedEdge.data as WorkflowGraphEdgeData | undefined}
            onSave={saveSelectedEdgeData}
            onClose={() => setSelectedEdgeId(null)}
          />
        ) : (
          <NodePalette
            nodeTypes={paletteNodeTypes}
            allNodeTypes={nodeTypes}
            channelInstances={connectorInstances}
            selectedChannelInstanceId={selectedChannelInstanceId}
            onSelectChannel={setSelectedChannelInstanceId}
            onDragStartNodeType={(nodeType, event) => {
              event.dataTransfer.setData("application/reactflow", nodeType.node_type);
              event.dataTransfer.effectAllowed = "move";
            }}
          />
        )}
      </div>
    </div>
  );
}

export function WorkflowEditorPage() {
  const { id } = useParams<{ id: string }>();
  if (!id) return null;

  return (
    <ReactFlowProvider>
      <WorkflowEditorInner workflowId={id} />
    </ReactFlowProvider>
  );
}
