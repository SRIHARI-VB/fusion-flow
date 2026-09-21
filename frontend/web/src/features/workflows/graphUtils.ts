import type { Edge, Node } from "@xyflow/react";
import type { NodeType, WorkflowGraphEdge, WorkflowGraphJson, WorkflowGraphNode, WorkflowNodeData } from "./types";
import { CONTAINER_HEADER_HEIGHT, CONTAINER_MIN_HEIGHT, CONTAINER_MIN_WIDTH } from "./nodes/ContainerNode";

/** The extra, client-only field denormalized onto every node's `data` so
 * `CardNode`/`ContainerNode` can render an icon/label/ports without a
 * React context — derived from the `GET /workflows/node-types` palette
 * list, looked up by `data.nodeType`. Stripped back out before the graph
 * is sent to the backend (see `toGraphJson`) — the backend's
 * `GraphNodeData` would silently ignore it anyway (pydantic's default
 * `extra="ignore"`), but stripping keeps `workflow_versions.graph` free
 * of derived data. */
export const NODE_META_KEY = "__meta";

//: React Flow visual node "type" for any node whose executor opts into
//: embedding (`can_contain_children`) - rendered by `ContainerNode`
//: instead of `CardNode`, regardless of its `kind` (Loop/Parallel are
//: "action", Try/Catch is "condition").
export const CONTAINER_RF_TYPE = "container";

export interface CardNodeData extends WorkflowNodeData {
  __meta?: NodeType;
}

function rfTypeFor(node: WorkflowGraphNode, meta: NodeType | undefined): string {
  if (meta?.can_contain_children) return CONTAINER_RF_TYPE;
  return node.type ?? meta?.kind ?? "action";
}

export function enrichNodes(
  nodes: WorkflowGraphNode[],
  nodeTypesByKey: Map<string, NodeType>,
): Node<CardNodeData>[] {
  return nodes.map((node) => {
    const meta = nodeTypesByKey.get(node.data.nodeType);
    return {
      id: node.id,
      type: rfTypeFor(node, meta),
      position: node.position ?? { x: 0, y: 0 },
      data: { ...node.data, __meta: meta },
      ...(node.parentId ? { parentId: node.parentId, extent: "parent" as const } : {}),
      ...(node.width ? { width: node.width } : {}),
      ...(node.height ? { height: node.height } : {}),
    };
  });
}

export function edgesFromJson(edges: WorkflowGraphEdge[]): Edge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle ?? undefined,
    targetHandle: edge.targetHandle ?? undefined,
    type: "default",
    data: edge.data ?? undefined,
    label: edge.data?.label ?? undefined,
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
        ...(node.parentId ? { parentId: node.parentId } : {}),
        ...(typeof node.width === "number" ? { width: node.width } : {}),
        ...(typeof node.height === "number" ? { height: node.height } : {}),
      };
    }),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? null,
      targetHandle: edge.targetHandle ?? null,
      ...(edge.data ? { data: edge.data } : {}),
    })),
  };
}

/** Gap kept between a container's fitted edge and its farthest child's own
 * right/bottom edge, so a snug-fit container doesn't clip a child's own
 * border/shadow. Applied once (not per side) since a child's `position` is
 * already relative to the container's top-left — this only pads the far
 * edge the bounding-box walk actually measures. */
const CONTAINER_FIT_PADDING = 24;

/** Fallback size for a child whose `measured` dimensions haven't been
 * reported yet (before React Flow's first `ResizeObserver` pass — e.g.
 * right after hydration or right after a fresh drop) — 256 matches
 * `CardNode`'s own fixed `w-64` width; 80 is a compact unconfigured card's
 * typical rendered height (header + one summary line). */
const CHILD_FALLBACK_WIDTH = 256;
const CHILD_FALLBACK_HEIGHT = 80;

/** Pure "does this container need to grow/shrink to fit its children"
 * calculation for the container auto-fit-to-children feature — walks every
 * node whose `parentId` is `containerId`, finds the bounding box of their
 * `position` + `measured` (or fallback) size, and returns the container
 * size that would snugly wrap them with `CONTAINER_FIT_PADDING` room to
 * spare and `CONTAINER_HEADER_HEIGHT` reserved above them for the
 * container's own header chrome. Returns `null` — "no resize needed" — when
 * the container has no children, isn't found, or the computed size already
 * matches its current `width`/`height`, so a caller that always applies a
 * non-null result can't get stuck in a resize -> children move -> resize
 * loop. Never mutates `nodes`; the caller (`WorkflowEditorPage.tsx`'s
 * auto-fit effect) is responsible for actually calling `setNodes`. */
export function fitContainerToChildren(
  containerId: string,
  nodes: Node<CardNodeData>[],
): { width: number; height: number } | null {
  const container = nodes.find((n) => n.id === containerId);
  if (!container) return null;

  const children = nodes.filter((n) => n.parentId === containerId);
  if (children.length === 0) return null;

  let maxRight = 0;
  let maxBottom = 0;
  for (const child of children) {
    const width = child.measured?.width ?? CHILD_FALLBACK_WIDTH;
    const height = child.measured?.height ?? CHILD_FALLBACK_HEIGHT;
    maxRight = Math.max(maxRight, child.position.x + width);
    maxBottom = Math.max(maxBottom, child.position.y + height);
  }

  const width = Math.max(CONTAINER_MIN_WIDTH, Math.round(maxRight + CONTAINER_FIT_PADDING));
  const height = Math.max(
    CONTAINER_MIN_HEIGHT,
    Math.round(maxBottom + CONTAINER_FIT_PADDING + CONTAINER_HEADER_HEIGHT),
  );

  const currentWidth = container.width ?? CONTAINER_MIN_WIDTH;
  const currentHeight = container.height ?? CONTAINER_MIN_HEIGHT;
  if (width === currentWidth && height === currentHeight) return null;

  return { width, height };
}
