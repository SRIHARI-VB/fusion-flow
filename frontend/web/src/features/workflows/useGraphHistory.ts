import { useCallback, useEffect, useRef, useState } from "react";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";
import type { Edge, Node } from "@xyflow/react";
import type { CardNodeData } from "./graphUtils";

type GraphSnapshot = { nodes: Node<CardNodeData>[]; edges: Edge[] };

const MAX_HISTORY = 50;
const DEBOUNCE_MS = 400;

/**
 * Debounced "watch and snapshot" undo/redo for the workflow canvas.
 *
 * Rather than instrumenting every one of the ~13 call sites in
 * `WorkflowEditorPage.tsx` that mutate `nodes`/`edges` (inline card edits,
 * inserting a component, connecting/dropping/dragging nodes, the config
 * drawers, deletes, ...), this watches the *committed* `nodes`/`edges`
 * state as a whole and, once it goes quiet for `DEBOUNCE_MS`, records the
 * snapshot from just before the quiet period as a single undo step. That
 * debounce is what coalesces an entire node-drag gesture (many rapid
 * `onNodesChange` position updates) - or a burst of rapid distinct edits -
 * into one undo step, and it automatically covers any mutation site
 * without needing to be kept in sync with the list above.
 */
export function useGraphHistory({
  nodes,
  edges,
  setNodes,
  setEdges,
  hasHydratedRef,
}: {
  nodes: Node<CardNodeData>[];
  edges: Edge[];
  setNodes: Dispatch<SetStateAction<Node<CardNodeData>[]>>;
  setEdges: Dispatch<SetStateAction<Edge[]>>;
  hasHydratedRef: MutableRefObject<boolean>;
}) {
  const pastRef = useRef<GraphSnapshot[]>([]);
  const futureRef = useRef<GraphSnapshot[]>([]);
  const prevSnapshotRef = useRef<GraphSnapshot>({ nodes, edges });
  const isApplyingHistoryRef = useRef(false);
  // Separate from `hasHydratedRef` (which only guards *whether* the initial
  // API load has happened at all): this absorbs the one nodes/edges update
  // that hydration itself produces as the new baseline, rather than
  // recording "empty canvas -> freshly loaded graph" as an undo-able step.
  const hydrationConsumedRef = useRef(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [undoAvailable, setUndoAvailable] = useState(false);
  const [redoAvailable, setRedoAvailable] = useState(false);

  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
      debounceRef.current = null;
    }

    // We just applied an undo/redo ourselves - absorb this update as the
    // new baseline instead of recording a fresh history entry for it.
    if (isApplyingHistoryRef.current) {
      isApplyingHistoryRef.current = false;
      prevSnapshotRef.current = { nodes, edges };
      return;
    }

    if (!hasHydratedRef.current) {
      prevSnapshotRef.current = { nodes, edges };
      return;
    }

    if (!hydrationConsumedRef.current) {
      hydrationConsumedRef.current = true;
      prevSnapshotRef.current = { nodes, edges };
      return;
    }

    debounceRef.current = setTimeout(() => {
      const previous = prevSnapshotRef.current;
      if (previous.nodes !== nodes || previous.edges !== edges) {
        pastRef.current = [...pastRef.current, previous].slice(-MAX_HISTORY);
        futureRef.current = [];
        setUndoAvailable(true);
        setRedoAvailable(false);
      }
      prevSnapshotRef.current = { nodes, edges };
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [nodes, edges, hasHydratedRef]);

  const undo = useCallback(() => {
    if (pastRef.current.length === 0) return;
    const previous = pastRef.current[pastRef.current.length - 1];
    pastRef.current = pastRef.current.slice(0, -1);
    futureRef.current = [...futureRef.current, { nodes, edges }].slice(-MAX_HISTORY);
    isApplyingHistoryRef.current = true;
    setNodes(previous.nodes);
    setEdges(previous.edges);
    setUndoAvailable(pastRef.current.length > 0);
    setRedoAvailable(true);
  }, [nodes, edges, setNodes, setEdges]);

  const redo = useCallback(() => {
    if (futureRef.current.length === 0) return;
    const next = futureRef.current[futureRef.current.length - 1];
    futureRef.current = futureRef.current.slice(0, -1);
    pastRef.current = [...pastRef.current, { nodes, edges }].slice(-MAX_HISTORY);
    isApplyingHistoryRef.current = true;
    setNodes(next.nodes);
    setEdges(next.edges);
    setRedoAvailable(futureRef.current.length > 0);
    setUndoAvailable(true);
  }, [nodes, edges, setNodes, setEdges]);

  return { undo, redo, undoAvailable, redoAvailable };
}
