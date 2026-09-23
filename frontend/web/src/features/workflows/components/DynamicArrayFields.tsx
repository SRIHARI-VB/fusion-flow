import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button, cn } from "@fusion-flow/ui";
import type { ResolvedField } from "../jsonSchemaForm";
import { DraftInput, DraftTextarea, TemplateHint } from "./DraftFields";
import { InsertVariableMenu } from "./InsertVariableMenu";

/**
 * Renders a repeatable field for `array_text`/`array_object`-kind
 * `ResolvedField`s (see `jsonSchemaForm.ts`) - the piece that makes
 * WhatsApp's buttons/list-rows/contacts fields (and any future
 * integration's own repeatable field) usable in the builder instead of
 * only editable as raw JSON. `ArrayObjectField` recurses for a sub-field
 * that is itself array-of-objects (e.g. an interactive list's
 * `sections[].rows`), so nesting depth isn't hardcoded to WhatsApp's
 * specific shapes.
 *
 * Plain `value`/`onChange` props throughout, not React Hook Form - these
 * are now mounted inline on every node card at once (see
 * `NodeInlineForm.tsx`), not inside a single per-selected-node drawer form
 * instance, so there's no shared `control` to bind to anymore. Text/textarea
 * leaves go through `DraftFields.tsx`'s local-draft-commit-on-blur inputs
 * for the same reason `CardNode.tsx`'s primary field already does - typing
 * shouldn't propagate a `setNodes` call on every keystroke.
 */

interface ArrayFieldProps {
  value: unknown;
  onChange: (next: unknown) => void;
  field: ResolvedField;
  /** Upstream-node output paths available for this node - threaded down so
   * each row/sub-field can offer the same "insert variable" affordance
   * `JsonObjectField` already has. */
  upstreamSuggestions?: { path: string; label: string }[];
}

export function ArrayTextField({ value, onChange, field, upstreamSuggestions = [] }: ArrayFieldProps) {
  const values: string[] = Array.isArray(value) ? (value as string[]) : [];

  function updateAt(index: number, next: string) {
    const copy = [...values];
    copy[index] = next;
    onChange(copy);
  }

  return (
    <div className="flex flex-col gap-2">
      {values.map((rowValue, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <DraftInput
            value={rowValue}
            onCommit={(next) => updateAt(index, next)}
            placeholder={`${field.label} ${index + 1}`}
          />
          <InsertVariableMenu
            suggestions={upstreamSuggestions}
            onInsert={(path) => updateAt(index, `${rowValue}{{${path}}}`)}
          />
          <button
            type="button"
            aria-label="Remove item"
            className="nodrag rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
            onClick={() => onChange(values.filter((_, i) => i !== index))}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" className="nodrag" onClick={() => onChange([...values, ""])}>
        <Plus className="h-3.5 w-3.5" />
        Add {field.label.toLowerCase()}
      </Button>
      {field.required && values.length === 0 && (
        <p className="text-xs text-destructive">{field.label} requires at least one item.</p>
      )}
    </div>
  );
}

function emptyRowFor(field: ResolvedField): Record<string, unknown> {
  const row: Record<string, unknown> = {};
  for (const sub of field.itemFields ?? []) {
    row[sub.key] = sub.kind === "array_text" || sub.kind === "array_object" ? [] : sub.kind === "boolean" ? false : "";
  }
  return row;
}

/** One sub-field inside an `ArrayObjectField` row, dispatched by kind -
 * mirrors `NodeInlineForm.tsx`'s own top-level per-kind dispatch, just for
 * the handful of primitive kinds that can appear nested inside a row
 * (never `recipient`/`auto_ref`/`suggested_select`/`json_object` - no
 * config field in this codebase nests one of those inside an array row
 * today). */
function ArrayObjectSubField({
  sub,
  value,
  onChange,
  upstreamSuggestions,
}: {
  sub: ResolvedField;
  value: unknown;
  onChange: (next: unknown) => void;
  upstreamSuggestions: { path: string; label: string }[];
}) {
  if (sub.kind === "array_text") {
    return <ArrayTextField value={value} onChange={onChange} field={sub} upstreamSuggestions={upstreamSuggestions} />;
  }
  if (sub.kind === "array_object") {
    return <ArrayObjectField value={value} onChange={onChange} field={sub} upstreamSuggestions={upstreamSuggestions} />;
  }
  if (sub.kind === "boolean") {
    return (
      <input
        type="checkbox"
        className="nodrag h-4 w-4"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  }
  if (sub.kind === "select") {
    return (
      <select
        className="nodrag h-9 rounded-md border border-input bg-card px-2 text-sm"
        value={typeof value === "string" ? value : ""}
        onChange={(e) => onChange(e.target.value)}
      >
        {!sub.required && <option value="">--</option>}
        {(sub.options ?? []).map((opt) => (
          <option key={opt} value={opt}>
            {opt}
          </option>
        ))}
      </select>
    );
  }
  if (sub.kind === "textarea") {
    const text = typeof value === "string" ? value : "";
    const nearLimit = typeof sub.maxLength === "number" && text.length >= sub.maxLength - 3;
    return (
      <div className="flex items-start gap-1.5">
        <div className="flex flex-1 flex-col gap-0.5">
          <DraftTextarea value={text} onCommit={onChange} maxLength={sub.maxLength} />
          {typeof sub.maxLength === "number" && (
            <span className={cn("self-end text-[10px]", nearLimit ? "text-destructive" : "text-muted-foreground")}>
              {text.length}/{sub.maxLength}
            </span>
          )}
        </div>
        <InsertVariableMenu suggestions={upstreamSuggestions} onInsert={(path) => onChange(`${text}{{${path}}}`)} />
      </div>
    );
  }
  // "text" / "number" - the only remaining leaf kinds a sub-field resolves to.
  const text = value === undefined || value === null ? "" : String(value);
  const nearLimit = typeof sub.maxLength === "number" && text.length >= sub.maxLength - 3;
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex flex-1 flex-col gap-0.5">
        <DraftInput
          type={sub.kind === "number" ? "number" : "text"}
          value={text}
          onCommit={(next) => onChange(sub.kind === "number" ? Number(next) || 0 : next)}
          maxLength={sub.maxLength}
        />
        {typeof sub.maxLength === "number" && (
          <span className={cn("self-end text-[10px]", nearLimit ? "text-destructive" : "text-muted-foreground")}>
            {text.length}/{sub.maxLength}
          </span>
        )}
      </div>
      {sub.kind === "text" && (
        <InsertVariableMenu suggestions={upstreamSuggestions} onInsert={(path) => onChange(`${text}{{${path}}}`)} />
      )}
    </div>
  );
}

export function ArrayObjectField({ value, onChange, field, upstreamSuggestions = [] }: ArrayFieldProps) {
  const rows: Record<string, unknown>[] = Array.isArray(value) ? (value as Record<string, unknown>[]) : [];

  function updateRow(index: number, patch: Record<string, unknown>) {
    onChange(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  return (
    <div className="flex flex-col gap-2">
      {rows.map((row, index) => (
        <div key={index} className="flex flex-col gap-2 rounded-md border border-border p-2">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              {field.label} {index + 1}
            </span>
            <button
              type="button"
              aria-label="Remove row"
              className="nodrag rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-destructive"
              onClick={() => onChange(rows.filter((_, i) => i !== index))}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>

          {(field.itemFields ?? []).map((sub) => (
            <div key={sub.key} className="flex flex-col gap-1">
              <label className="text-[11px] text-muted-foreground">
                {sub.label}
                {sub.required && <span className="text-destructive"> *</span>}
              </label>
              <ArrayObjectSubField
                sub={sub}
                value={row[sub.key]}
                onChange={(next) => updateRow(index, { [sub.key]: next })}
                upstreamSuggestions={upstreamSuggestions}
              />
            </div>
          ))}
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" className="nodrag" onClick={() => onChange([...rows, emptyRowFor(field)])}>
        <Plus className="h-3.5 w-3.5" />
        Add {field.label.toLowerCase()}
      </Button>
      {field.required && rows.length === 0 && (
        <p className="text-xs text-destructive">{field.label} requires at least one item.</p>
      )}
    </div>
  );
}

interface JsonObjectFieldProps {
  value: unknown;
  onChange: (next: Record<string, unknown>) => void;
  field: ResolvedField;
  /** Upstream-node output paths available for this node - rendered as an
   * "insert variable" affordance next to the textarea/rows. */
  upstreamSuggestions?: { path: string; label: string }[];
}

/** A plain string value, or - for something shaped like Instagram/WhatsApp's
 * `buttons`/`sections` params (an array of flat objects, e.g.
 * `[{"title": "Today", "payload": "DAY_TODAY"}, ...]`) - the array kept
 * as real objects instead of being flattened to a JSON string, so it can
 * render as its own small structured editor (see `isObjectArray`/
 * `JsonArrayRowEditor` below) rather than forcing "Advanced: edit as
 * JSON" just to add a button. */
interface KeyValueRow {
  key: string;
  value: string | Record<string, unknown>[];
}

function isObjectArray(val: unknown): val is Record<string, unknown>[] {
  return (
    Array.isArray(val) &&
    val.length > 0 &&
    val.every((item) => item !== null && typeof item === "object" && !Array.isArray(item))
  );
}

/** Turns a `dict[str, Any]`-typed config value into the row editor's own
 * local shape. An array-of-objects value (see `isObjectArray`) is kept
 * as real objects; anything else non-string is stringified so the row
 * editor never crashes on an unusual saved value - a user who needs to
 * keep some OTHER nested shape (a plain object, a mixed array) intact
 * can reach for "Advanced: edit as JSON" instead, which round-trips the
 * real value untouched. */
function rowsFromObject(value: unknown): KeyValueRow[] {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value as Record<string, unknown>).map(([key, val]) => ({
    key,
    value: isObjectArray(val) ? val : typeof val === "string" ? val : JSON.stringify(val),
  }));
}

/** Every key seen across an array-of-objects value's items, in first-seen
 * order - the column set for `JsonArrayRowEditor`. An item missing a key
 * another item has just renders that cell empty, rather than the whole
 * row editor assuming every item shares one exact shape. */
function columnsFor(items: Record<string, unknown>[]): string[] {
  const seen: string[] = [];
  for (const item of items) {
    for (const key of Object.keys(item)) {
      if (!seen.includes(key)) seen.push(key);
    }
  }
  return seen;
}

interface JsonArrayRowEditorProps {
  items: Record<string, unknown>[];
  onChange: (next: Record<string, unknown>[]) => void;
}

/** The structured editor for a `buttons`/`sections`-shaped param value -
 * one row per array item, one small input per key found across those
 * items (see `columnsFor`), with add/remove-item controls. Falls back to
 * a single generic "value" column for a brand-new, still-empty array
 * (there's nothing to infer a shape from yet). */
function JsonArrayRowEditor({ items, onChange }: JsonArrayRowEditorProps) {
  const columns = columnsFor(items);

  function updateItem(index: number, key: string, next: string) {
    onChange(items.map((item, i) => (i === index ? { ...item, [key]: next } : item)));
  }

  function addItem() {
    const blank = Object.fromEntries((columns.length > 0 ? columns : ["title", "payload"]).map((c) => [c, ""]));
    onChange([...items, blank]);
  }

  function removeItem(index: number) {
    onChange(items.filter((_, i) => i !== index));
  }

  return (
    <div className="flex flex-1 flex-col gap-1.5 rounded-md border border-border bg-background p-1.5">
      {items.map((item, index) => (
        <div key={index} className="flex items-center gap-1.5">
          {columns.map((column) => (
            <DraftInput
              key={column}
              value={typeof item[column] === "string" ? (item[column] as string) : JSON.stringify(item[column] ?? "")}
              onCommit={(next) => updateItem(index, column, next)}
              placeholder={column}
              className="flex-1"
            />
          ))}
          <button
            type="button"
            aria-label="Remove item"
            className="nodrag rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              removeItem(index);
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="nodrag w-fit"
        onMouseDown={(e) => e.stopPropagation()}
        onClick={(e) => {
          e.stopPropagation();
          addItem();
        }}
      >
        <Plus className="h-3.5 w-3.5" />
        Add item
      </Button>
    </div>
  );
}

function objectFromRows(rows: KeyValueRow[]): Record<string, unknown> {
  return Object.fromEntries(rows.filter((row) => row.key.trim().length > 0).map((row) => [row.key, row.value]));
}

/** A `dict[str, Any]`-typed config field (`filters`/`fields`/`params`/
 * `outputs` - see `jsonSchemaForm.ts`'s `"json_object"` kind). Neither WATI
 * nor Pabbly Chatflow ever shows a non-technical user raw JSON for this
 * shape (a WhatsApp header/param map), so this defaults to a plain
 * key/value row editor - same add/remove-row pattern as `ArrayTextField`
 * above - and only falls back to the original pretty-printed-JSON textarea
 * behind an opt-in "Advanced: edit as JSON" toggle, for the rare case where
 * a value is genuinely a nested object/array rather than a flat string
 * (the row editor stringifies those for display, so round-tripping through
 * it would flatten them - advanced mode keeps the real shape intact). */
export function JsonObjectField({ value, onChange, field, upstreamSuggestions = [] }: JsonObjectFieldProps) {
  const [advanced, setAdvanced] = useState(false);
  const [rows, setRows] = useState<KeyValueRow[]>(() => rowsFromObject(value));
  const [text, setText] = useState(() => JSON.stringify(value ?? {}, null, 2));
  const [invalid, setInvalid] = useState(false);

  function updateRows(nextRows: KeyValueRow[]) {
    setRows(nextRows);
    onChange(objectFromRows(nextRows));
  }

  function updateRowAt(index: number, patch: Partial<KeyValueRow>) {
    updateRows(rows.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  }

  function commit(nextText: string) {
    try {
      const parsed = JSON.parse(nextText || "{}");
      onChange(parsed);
      setInvalid(false);
    } catch {
      setInvalid(true);
    }
  }

  function switchToAdvanced() {
    setText(JSON.stringify(value ?? {}, null, 2));
    setInvalid(false);
    setAdvanced(true);
  }

  function switchToSimple() {
    setRows(rowsFromObject(value));
    setAdvanced(false);
  }

  if (advanced) {
    return (
      <div className="flex flex-col gap-1">
        <div className="flex items-start gap-1">
          <DraftTextarea
            value={text}
            onCommit={(next) => {
              setText(next);
              commit(next);
            }}
            rows={4}
            className={cn("font-mono text-xs", invalid && "border-destructive")}
          />
          <InsertVariableMenu suggestions={upstreamSuggestions} onInsert={(path) => setText((t) => `${t}{{${path}}}`)} />
        </div>
        {invalid && <p className="text-xs text-destructive">Invalid JSON</p>}
        <button
          type="button"
          className="nodrag self-start text-[11px] text-muted-foreground underline hover:text-foreground"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            switchToSimple();
          }}
        >
          Use simple editor
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {rows.map((row, index) => (
        <div key={index} className="flex items-start gap-1.5">
          <DraftInput
            value={row.key}
            onCommit={(next) => updateRowAt(index, { key: next })}
            placeholder="Key"
            className="w-2/5"
          />
          {isObjectArray(row.value) ? (
            // A `buttons`/`sections`-shaped value (an array of flat
            // objects) - a proper add/remove-item editor instead of a
            // flattened JSON string, so e.g. Instagram/WhatsApp button
            // templates are as editable as any other structured field.
            <JsonArrayRowEditor items={row.value} onChange={(next) => updateRowAt(index, { value: next })} />
          ) : (
            // A dict value is just as likely to be a long/multi-line
            // message (a DM's "text", a button template's prompt, ...) as
            // a short id - a single-line input made those genuinely hard
            // to edit. A small resizable textarea handles both without a
            // separate "is this a long field" heuristic; newlines the
            // author types here are sent through exactly as typed (the
            // adapters pass `params` values through untouched).
            <div className="flex flex-1 flex-col gap-0.5">
              <DraftTextarea
                value={row.value as string}
                onCommit={(next) => updateRowAt(index, { value: next })}
                placeholder="Value"
                rows={2}
                className="min-h-[38px] w-full resize-y"
              />
              <TemplateHint value={row.value as string} suggestions={upstreamSuggestions} />
            </div>
          )}
          {!isObjectArray(row.value) && (
            <InsertVariableMenu
              suggestions={upstreamSuggestions}
              onInsert={(path) => updateRowAt(index, { value: `${row.value}{{${path}}}` })}
            />
          )}
          <button
            type="button"
            aria-label="Remove field"
            className="nodrag mt-1.5 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => {
              e.stopPropagation();
              updateRows(rows.filter((_, i) => i !== index));
            }}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <div className="flex items-center gap-3">
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="nodrag"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            updateRows([...rows, { key: "", value: "" }]);
          }}
        >
          <Plus className="h-3.5 w-3.5" />
          Add {field.label.toLowerCase()}
        </Button>
        <button
          type="button"
          className="nodrag text-[11px] text-muted-foreground underline hover:text-foreground"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={(e) => {
            e.stopPropagation();
            switchToAdvanced();
          }}
        >
          Advanced: edit as JSON
        </button>
      </div>
    </div>
  );
}
