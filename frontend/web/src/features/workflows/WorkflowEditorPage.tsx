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
import type { NodeType, ValidationIssue, WorkflowGraphJson, WorkflowRunDetail } from "./types";
import { CardNode } from "./nodes/CardNode";
import { NodePalette } from "./components/NodePalette";
import { NodeConfigDrawer } from "./components/NodeConfigDrawer";
import { ValidationPanel } from "./components/ValidationPanel";
import { RunStepTrace } from "./components/RunStepTrace";
import { enrichNodes, edgesFromJson, toGraphJson, type CardNodeData } from "./graphUtils";

const nodeTypesForFlow = { trigger: CardNode, action: CardNode, condition: CardNode };

const EMPTY_GRAPH: WorkflowGraphJson = { nodes: [], edges: [] };

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

      const position = reactFlow.screenToFlowPosition({ x: event.clientX, y: event.clientY });
      const id = `node_${Math.random().toString(36).slice(2, 10)}`;
      const newNode: Node<CardNodeData> = {
        id,
        type: nodeType.kind,
        position,
        data: { nodeType: nodeType.node_type, label: nodeType.label, config: {}, __meta: nodeType },
      };
      setNodes((nds) => [...nds, newNode]);
    },
    [nodeTypesByKey, reactFlow, setNodes],
  );

  function onNodeClick(_event: React.MouseEvent, node: Node) {
    setSelectedNodeId(node.id);
  }

  function onPaneClick() {
    setSelectedNodeId(null);
  }

  const selectedNode = nodes.find((n) => n.id === selectedNodeId) ?? null;
  const selectedNodeType: NodeType | undefined = selectedNode
    ? nodeTypesByKey.get(selectedNode.data.nodeType)
    : undefined;

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
    setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId));
    setEdges((eds) => eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId));
    setSelectedNodeId(null);
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
                  <RunStepTrace steps={lastRun.steps} />
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
