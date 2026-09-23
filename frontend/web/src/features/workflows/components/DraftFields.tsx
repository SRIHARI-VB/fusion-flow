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

/** A field value's `{{...}}` tokens, translated to plain English - so
 * "Customer Id" showing `{{find-or-create-customer-pb.customer.id}}"`
 * reads as "Uses: Customer's Id from Find or Create Customer" instead of
 * making a non-technical author decode raw node-id/path syntax. `trigger.*`
 * tokens (the one namespace that's never an `upstreamSuggestions` entry -
 * it's the run's trigger payload, not a completed node's output) get a
 * generic fallback description instead of being left as raw path text. */
export function describeTemplateTokens(
  value: string,
  suggestions: { path: string; label: string }[],
): string[] {
  const matches = value.match(/\{\{\s*([\w.-]+)\s*\}\}/g);
  if (!matches) return [];
  const seen = new Set<string>();
  const descriptions: string[] = [];
  for (const raw of matches) {
    const path = raw.replace(/\{\{\s*|\s*\}\}/g, "");
    if (seen.has(path)) continue;
    seen.add(path);
    const suggestion = suggestions.find((s) => s.path === path);
    if (suggestion) {
      descriptions.push(suggestion.label);
    } else if (path.startsWith("trigger.")) {
      descriptions.push(`the incoming event's "${path.slice("trigger.".length)}"`);
    } else {
      descriptions.push(path);
    }
  }
  return descriptions;
}

/** A field value's live "Uses: ..." translation - mounted explicitly by
 * call sites that already have a `flex flex-col` wrapper around their
 * input (so adding this line never risks changing an input's width/flex
 * sizing the way returning it bundled inside `DraftInput`/`DraftTextarea`
 * itself would for the many callers that rely on their `className` width
 * utility - e.g. `w-2/5` - applying directly to the input in a horizontal
 * row). */
export function TemplateHint({ value, suggestions }: { value: string; suggestions?: { path: string; label: string }[] }) {
  const descriptions = describeTemplateTokens(value, suggestions ?? []);
  if (descriptions.length === 0) return null;
  return <p className="text-[10px] text-muted-foreground">Uses: {descriptions.join(", ")}</p>;
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
