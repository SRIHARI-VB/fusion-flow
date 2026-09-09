import type { Edge, Node } from "@xyflow/react";
import type { NodeType, WorkflowGraphEdge, WorkflowGraphJson, WorkflowGraphNode, WorkflowNodeData } from "./types";

/** The extra, client-only field denormalized onto every node's `data` so
 * `CardNode` can render an icon/label/ports without a React context —
 * derived from the `GET /workflows/node-types` palette list, looked up by
 * `data.nodeType`. Stripped back out before the graph is sent to the
 * backend (see `toGraphJson`) — the backend's `GraphNodeData` would
 * silently ignore it anyway (pydantic's default `extra="ignore"`), but
 * stripping keeps `workflow_versions.graph` free of derived data. */
export const NODE_META_KEY = "__meta";

export interface CardNodeData extends WorkflowNodeData {
  __meta?: NodeType;
}

export function enrichNodes(
  nodes: WorkflowGraphNode[],
  nodeTypesByKey: Map<string, NodeType>,
): Node<CardNodeData>[] {
  return nodes.map((node) => ({
    id: node.id,
    type: node.type ?? nodeTypesByKey.get(node.data.nodeType)?.kind ?? "action",
    position: node.position ?? { x: 0, y: 0 },
    data: { ...node.data, __meta: nodeTypesByKey.get(node.data.nodeType) },
  }));
}

export function edgesFromJson(edges: WorkflowGraphEdge[]): Edge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle ?? undefined,
    targetHandle: edge.targetHandle ?? undefined,
    type: "default",
  }));
}

/** Inverse of `enrichNodes`/`edgesFromJson` — strips xyflow-internal
 * fields (`__meta`, `selected`, `measured`, ...) down to exactly the shape
 * `engine.graph.WorkflowGraph` expects. */
export function toGraphJson(nodes: Node<CardNodeData>[], edges: Edge[]): WorkflowGraphJson {
  return {
    nodes: nodes.map((node) => {
      const { __meta, ...rest } = node.data;
      void __meta;
      return {
        id: node.id,
        type: node.type,
        position: { x: node.position.x, y: node.position.y },
        data: rest as WorkflowNodeData,
      };
    }),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? null,
      targetHandle: edge.targetHandle ?? null,
    })),
  };
}
