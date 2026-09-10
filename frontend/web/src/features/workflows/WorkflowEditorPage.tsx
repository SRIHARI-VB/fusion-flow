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
  type OnNodeDrag,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { ArrowLeft, PlayCircle, Save, ShieldCheck, Upload } from "lucide-react";
import { Button, Input } from "@fusion-flow/ui";
import {
  getWorkflow,
  listNodeTypes,
  listWorkflowVersions,
  publishWorkflow,
  simulateWorkflow,
  updateWorkflow,
} from "./api";
import type { NodeType, ValidationIssue, WorkflowGraphEdgeData, WorkflowGraphJson, WorkflowRunDetail } from "./types";
import { CardNode } from "./nodes/CardNode";
import { ContainerNode, CONTAINER_MIN_HEIGHT, CONTAINER_MIN_WIDTH } from "./nodes/ContainerNode";
import { NodePalette } from "./components/NodePalette";
import { NodeConfigDrawer } from "./components/NodeConfigDrawer";
import { EdgeConfigDrawer } from "./components/EdgeConfigDrawer";
import { ValidationPanel } from "./components/ValidationPanel";
import { RunStepTrace } from "./components/RunStepTrace";
import {
  CONTAINER_RF_TYPE,
  enrichNodes,
  edgesFromJson,
  toGraphJson,
  type CardNodeData,
} from "./graphUtils";

const nodeTypesForFlow = {
  trigger: CardNode,
  action: CardNode,
  condition: CardNode,
  [CONTAINER_RF_TYPE]: ContainerNode,
};

const EMPTY_GRAPH: WorkflowGraphJson = { nodes: [], edges: [] };

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

  const { data: workflow } = useQuery({ queryKey: ["workflow", workflowId], queryFn: () => getWorkflow(workflowId) });
  const { data: versions } = useQuery({
    queryKey: ["workflow-versions", workflowId],
    queryFn: () => listWorkflowVersions(workflowId),
  });
  const { data: nodeTypes = [] } = useQuery({ queryKey: ["workflow-node-types"], queryFn: listNodeTypes });

  const nodeTypesByKey = useMemo(() => new Map(nodeTypes.map((nt) => [nt.node_type, nt])), [nodeTypes]);
  const latestVersion = versions?.[0];

  const [name, setName] = useState("");
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<CardNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [autosave, setAutosave] = useState(false);
  const [validationIssues, setValidationIssues] = useState<ValidationIssue[] | null>(null);
  const [showValidation, setShowValidation] = useState(false);
  const [showTestPanel, setShowTestPanel] = useState(false);
  const [testPayload, setTestPayload] = useState("{}");
  const [lastRun, setLastRun] = useState<WorkflowRunDetail | null>(null);

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

      const newNode: Node<CardNodeData> = {
        id,
        type: nodeType.can_contain_children ? CONTAINER_RF_TYPE : nodeType.kind,
        position: container
          ? { x: absolutePosition.x - container.position.x, y: absolutePosition.y - container.position.y }
          : absolutePosition,
        data: {
          nodeType: nodeType.node_type,
          label: nodeType.label,
          config: nodeType.default_config ?? {},
          __meta: nodeType,
        },
        ...(container ? { parentId: container.id, extent: "parent" as const } : {}),
      };
      setNodes((nds) => [...nds, newNode]);
    },
    [nodeTypesByKey, nodes, reactFlow, setNodes],
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
    <div className="flex h-[calc(100vh-6rem)] flex-col overflow-hidden rounded-lg border border-border bg-background">
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
          <Button variant="outline" size="sm" onClick={handleSave} disabled={updateMutation.isPending}>
            <Save className="h-4 w-4" />
            {updateMutation.isPending ? "Saving..." : "Save"}
          </Button>
          <Button size="sm" onClick={handlePublish} disabled={publishMutation.isPending}>
            <Upload className="h-4 w-4" />
            {publishMutation.isPending ? "Publishing..." : "Publish"}
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
            nodeTypes={nodeTypes}
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
