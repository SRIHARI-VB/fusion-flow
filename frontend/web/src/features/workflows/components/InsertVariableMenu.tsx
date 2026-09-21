import { Braces } from "lucide-react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@fusion-flow/ui";

/**
 * Small "insert variable" popover attached next to a freeform config field
 * (`text`/`json_object` - see `NodeInlineForm.tsx`/`DynamicArrayFields.tsx`)
 * - lists every upstream node's declared `output_schema` leaf paths
 * (`WorkflowEditorPage.tsx`'s backward-BFS-derived `upstreamSuggestionsByNode`,
 * flattened via `jsonSchemaForm.ts::flattenOutputPaths`), each rendered as
 * a clickable `{{path}}` row. Renders nothing when there's nothing to
 * offer (a node with no upstream nodes, or none of them declaring an
 * `output_schema` yet).
 */

interface InsertVariableMenuProps {
  suggestions: { path: string; label: string }[];
  onInsert: (path: string) => void;
}

export function InsertVariableMenu({ suggestions, onInsert }: InsertVariableMenuProps) {
  if (suggestions.length === 0) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger>
        <button
          type="button"
          aria-label="Insert variable"
          title="Insert variable from an upstream node"
          className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <Braces className="h-3.5 w-3.5" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-h-64 w-64 overflow-y-auto">
        {suggestions.map((s) => (
          <DropdownMenuItem key={s.path} className="flex flex-col items-start gap-0.5" onClick={() => onInsert(s.path)}>
            <span className="font-mono text-xs text-foreground">{`{{${s.path}}}`}</span>
            <span className="text-[10px] text-muted-foreground">{s.label}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
