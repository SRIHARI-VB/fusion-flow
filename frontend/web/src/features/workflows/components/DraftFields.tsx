import { useEffect, useState } from "react";
import { Input, Textarea, type InputProps, type TextareaProps } from "@fusion-flow/ui";

/**
 * Shared "local draft, commit on blur" input primitive for every free-text
 * field now permanently mounted inline on a React Flow node card (see the
 * "everything configures on the card" redesign - `NodeInlineForm.tsx` and
 * `DynamicArrayFields.tsx` both use this). Committing every keystroke
 * straight into `data.config` would call `setNodes` on every keystroke,
 * which recomputes the whole canvas's per-node state (upstream-suggestion
 * maps, undo/redo history, the container auto-fit watcher) for every node
 * currently rendered - now ALL of them, not just one selected node behind
 * a drawer. Buffering in local state and committing once on blur (or Enter,
 * for a single-line input) keeps that expensive propagation to real
 * "I'm done editing this field" moments, exactly the pattern `CardNode.tsx`'s
 * inline-editable primary field already established for this same reason.
 *
 * `value` from the parent always wins once focus leaves the field (so an
 * external change - undo/redo, the default-autofill effect, another tab
 * editing the same node - is never silently overwritten) but never fights
 * the user's own keystrokes while they're mid-edit.
 */

function useDraft(value: string, onCommit: (next: string) => void) {
  const [draft, setDraft] = useState(value);
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (!editing) setDraft(value);
  }, [value, editing]);

  function commit() {
    setEditing(false);
    if (draft !== value) onCommit(draft);
  }

  return { draft, setDraft, commit, onFocus: () => setEditing(true) };
}

interface DraftInputProps extends Omit<InputProps, "value" | "onChange" | "onBlur" | "onFocus"> {
  value: string;
  onCommit: (next: string) => void;
}

export function DraftInput({ value, onCommit, className, ...props }: DraftInputProps) {
  const { draft, setDraft, commit, onFocus } = useDraft(value, onCommit);
  return (
    <Input
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onFocus={onFocus}
      onBlur={commit}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      className={`nodrag nopan ${className ?? ""}`}
      {...props}
    />
  );
}

interface DraftTextareaProps extends Omit<TextareaProps, "value" | "onChange" | "onBlur" | "onFocus"> {
  value: string;
  onCommit: (next: string) => void;
}

export function DraftTextarea({ value, onCommit, className, ...props }: DraftTextareaProps) {
  const { draft, setDraft, commit, onFocus } = useDraft(value, onCommit);
  return (
    <Textarea
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onFocus={onFocus}
      onBlur={commit}
      onMouseDown={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
      className={`nodrag nopan ${className ?? ""}`}
      {...props}
    />
  );
}
