import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import type { NodeType } from "../types";
import { listModules } from "../api";
import { resolveFields, type ResolvedField } from "../jsonSchemaForm";
import { ArrayObjectField, ArrayTextField, JsonObjectField } from "./DynamicArrayFields";
import { DraftInput, DraftTextarea, TemplateHint } from "./DraftFields";
import { InsertVariableMenu } from "./InsertVariableMenu";
import { AskChoiceSourceField, DEFAULT_STATIC_SOURCE, type AskChoiceSource } from "./AskChoiceSourceField";
import { RecordModuleFields } from "./RecordModuleFields";
import { SendMessageContentField, DEFAULT_TEXT_CONTENT, type SendMessageContent } from "./SendMessageContentField";

/**
 * Every field of a node's `config_schema`, rendered directly on its card -
 * mounted by `CardNode.tsx`/`ContainerNode.tsx` only while that card is
 * expanded (see `NodePreview.tsx`'s collapsed bubble/summary view, shown
 * the rest of the time - the "collapsed by default, click to expand"
 * redesign; no more side-panel drawer either way). Extracted from the old
 * `NodeConfigDrawer.tsx` so the exact same field-kind dispatch and bespoke
 * per-node-type overrides (`AskChoiceSourceField`, `SendMessageContentField`,
 * `RecordModuleFields`) have one source of truth used by both leaf cards
 * and containers.
 *
 * Deliberately no React Hook Form / Zod here. RHF made sense for the old
 * drawer because it was a single form instance mounted only for whichever
 * one node was selected, discarding its own local edits until "Apply." This
 * form can still be mounted for more than one expanded node at once (expand
 * state is independent per card) - committing every keystroke straight into
 * `onConfigChange` (which bubbles to `setNodes`) would recompute the whole
 * canvas's derived state (upstream-suggestion maps, undo/redo history, the
 * container auto-fit watcher) on every keystroke, for every expanded node.
 * Instead: discrete fields (select/boolean/array add-remove) commit
 * immediately on change; free-text fields (text/textarea/number) go through
 * `DraftFields.tsx`'s local-draft-commit-on-blur inputs, the same pattern
 * `CardNode.tsx`'s primary field already established. Required/maxLength
 * validation is enforced by the schema itself (character counters below) -
 * full structural/shape validation still happens independently at publish
 * time via the backend + `ValidationPanel.tsx`, exactly as before.
 */

/** Config keys these node-type families render with a bespoke editor
 * instead of the generic per-field loop below. */
const HIDDEN_FIELD_KEYS_BY_NODE_TYPE: Record<string, string[]> = {
  "whatsapp.ask_choice": ["source"],
  "whatsapp.send_message": ["content"],
  "records.query": ["module", "filters", "item_id"],
  "records.upsert": ["module", "fields", "item_id"],
};

/** Human-readable stand-ins for an `"auto_ref"` field's `ref_suffix` (see
 * `jsonSchemaForm.ts`'s `"auto_ref"` kind) - shown in the collapsed
 * "Using: ..." line instead of the raw suffix. */
const AUTO_REF_LABELS: Record<string, string> = {
  recipients: "the list from the trigger",
  message_id: "the message that triggered this",
};

function autoRefFriendlyLabel(refSuffix: string | undefined): string {
  if (refSuffix && AUTO_REF_LABELS[refSuffix]) return AUTO_REF_LABELS[refSuffix];
  return "the matching value from an earlier step";
}

interface AutoRefFieldRowProps {
  field: ResolvedField;
  value: string;
  onChange: (next: string) => void;
  upstreamSuggestions: { path: string; label: string }[];
  expanded: boolean;
  onToggleExpanded: (next: boolean) => void;
}

/** Renders an `"auto_ref"`-kind field - a plain string config value that
 * should almost always hold an upstream reference (`{{node_id.<ref_suffix>}}`)
 * rather than something the author types by hand. Collapsed by default to
 * a one-line "Using: ..." summary, with a manual override for the rare
 * case the author wants something else. Sibling to the `"recipient"`
 * kind's own bespoke collapsed-line handling below - `"recipient"` is
 * really `auto_ref` hardcoded to `.from`, predating this more general
 * mechanism. */
function AutoRefFieldRow({ field, value, onChange, upstreamSuggestions, expanded, onToggleExpanded }: AutoRefFieldRowProps) {
  const suggestion = field.ref_suffix
    ? upstreamSuggestions.find((s) => s.path.endsWith(`.${field.ref_suffix}`))
    : undefined;

  if (!expanded) {
    return (
      <div className="flex items-center justify-between gap-2 rounded-md border border-input bg-muted/40 px-2.5 py-1.5 text-xs text-muted-foreground">
        <span>
          Using: <span className="font-medium text-foreground">{autoRefFriendlyLabel(field.ref_suffix)}</span>
        </span>
        <button
          type="button"
          className="nodrag shrink-0 text-xs font-medium text-primary underline"
          onClick={() => onToggleExpanded(true)}
        >
          Use something else
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center gap-1.5">
        <DraftInput value={value} onCommit={onChange} />
        <InsertVariableMenu suggestions={upstreamSuggestions} onInsert={(path) => onChange(`${value}{{${path}}}`)} />
      </div>
      {suggestion && (
        <button
          type="button"
          className="nodrag self-start text-xs font-medium text-primary underline"
          onClick={() => {
            onChange(`{{${suggestion.path}}}`);
            onToggleExpanded(false);
          }}
        >
          Use default ({autoRefFriendlyLabel(field.ref_suffix)})
        </button>
      )}
    </div>
  );
}

interface NodeInlineFormProps {
  nodeType: NodeType;
  config: Record<string, unknown>;
  onConfigChange: (patch: Record<string, unknown>) => void;
  /** Upstream nodes' declared output paths, reachable by following edges
   * backward from this node - offered via an "insert variable" picker
   * next to freeform reference fields, and used to auto-fill `recipient`/
   * `auto_ref` fields below. */
  upstreamSuggestions?: { path: string; label: string }[];
}

export function NodeInlineForm({ nodeType, config, onConfigChange, upstreamSuggestions = [] }: NodeInlineFormProps) {
  const { data: modules = [] } = useQuery({ queryKey: ["workflow-modules"], queryFn: listModules });

  // Per-field-key toggles for the "collapsed by default, expand to
  // override" affordances below - keyed by `field.key` rather than one
  // boolean each since either kind of field can appear more than once
  // across a node type's config (rare, but not impossible).
  const [expandedSuggestedSelects, setExpandedSuggestedSelects] = useState<Record<string, boolean>>({});
  const [expandedRecipients, setExpandedRecipients] = useState<Record<string, boolean>>({});
  const [expandedAutoRefs, setExpandedAutoRefs] = useState<Record<string, boolean>>({});

  const hiddenFieldKeys = HIDDEN_FIELD_KEYS_BY_NODE_TYPE[nodeType.node_type];
  const fields = resolveFields(nodeType.config_schema, nodeType.field_suggestions).filter(
    (field) => !hiddenFieldKeys?.includes(field.key),
  );

  // Stable primitive key derived from `upstreamSuggestions` - the default-
  // fill effect below depends on this instead of the array itself, since
  // `upstreamSuggestions` is a fresh array reference on every render (its
  // owner recomputes it per node on every canvas change) but should only
  // actually re-run the fill when which paths are reachable changes, not
  // on every keystroke anywhere in the graph.
  const upstreamKey = upstreamSuggestions.map((s) => s.path).join("|");

  // Auto-fill defaults for discriminated-union/reference fields the
  // instant a matching upstream value becomes reachable (generalized from
  // the old drawer's "on node selection" effect - there's no more
  // selection moment to hang this off of, so it now reacts to
  // `upstreamKey` becoming non-empty/changing instead, which fires at
  // whichever point is actually true: immediately for a node dropped
  // already wired via a saved graph/component fragment, or the moment the
  // author connects an edge for one dropped fresh from the palette). Only
  // ever fills a field that's still blank - an existing value (loaded or
  // author-typed) is never overwritten.
  useEffect(() => {
    const patch: Record<string, unknown> = {};
    if (nodeType.node_type === "whatsapp.ask_choice" && (!config.source || typeof config.source !== "object")) {
      patch.source = DEFAULT_STATIC_SOURCE;
    }
    if (nodeType.node_type === "whatsapp.send_message" && (!config.content || typeof config.content !== "object")) {
      patch.content = DEFAULT_TEXT_CONTENT;
    }
    for (const field of fields) {
      if (field.kind === "recipient" && !config[field.key]) {
        const suggestion = upstreamSuggestions.find((s) => s.path.endsWith(".from"));
        if (suggestion) patch[field.key] = `{{${suggestion.path}}}`;
      }
      if (field.kind === "auto_ref" && field.ref_suffix) {
        const existing = config[field.key];
        if (existing === undefined || existing === null || existing === "") {
          const suggestion = upstreamSuggestions.find((s) => s.path.endsWith(`.${field.ref_suffix}`));
          if (suggestion) patch[field.key] = `{{${suggestion.path}}}`;
        }
      }
    }
    if (Object.keys(patch).length > 0) onConfigChange(patch);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeType.node_type, upstreamKey]);

  function insertVariable(key: string, path: string) {
    const current = config[key];
    onConfigChange({ [key]: `${typeof current === "string" ? current : ""}{{${path}}}` });
  }

  const hasBespokeSection =
    nodeType.node_type === "whatsapp.ask_choice" ||
    nodeType.node_type === "whatsapp.send_message" ||
    nodeType.node_type === "records.query" ||
    nodeType.node_type === "records.upsert";

  if (fields.length === 0 && !hasBespokeSection) {
    return <p className="text-xs italic text-muted-foreground">This node type has no configurable fields.</p>;
  }

  return (
    <div className="flex flex-col gap-3">
      {fields.map((field) => {
        const rawValue = config[field.key];
        const textValue = typeof rawValue === "string" ? rawValue : "";
        const charCount = textValue.length;
        const nearLimit = typeof field.maxLength === "number" && charCount >= field.maxLength - 3;

        // An upstream trigger's `.from`-shaped output, if one is reachable,
        // and this field's own current value - used to decide between the
        // collapsed "Sending to: ..." line and the plain text input. The
        // default-fill effect above already writes the real `{{path}}`
        // expression into this field when it's still blank, so "still
        // showing the collapsed line" means "value is blank OR still
        // exactly that auto-filled expression."
        const recipientSuggestion =
          field.kind === "recipient" ? upstreamSuggestions.find((s) => s.path.endsWith(".from")) : undefined;
        const recipientIsDefault = !textValue || textValue === `{{${recipientSuggestion?.path}}}`;
        const recipientExpanded = expandedRecipients[field.key] ?? false;

        return (
          <div key={field.key} className="flex flex-col gap-1">
            <div className="flex items-center justify-between">
              <label className="text-[11px] font-medium text-muted-foreground">
                {field.label}
                {field.required && <span className="text-destructive"> *</span>}
              </label>
              {(field.kind === "text" || field.kind === "textarea" || field.kind === "recipient") && (
                <InsertVariableMenu suggestions={upstreamSuggestions} onInsert={(path) => insertVariable(field.key, path)} />
              )}
            </div>

            {field.kind === "boolean" && (
              <input
                type="checkbox"
                className="nodrag h-4 w-4 rounded border-input"
                checked={Boolean(rawValue)}
                onChange={(e) => onConfigChange({ [field.key]: e.target.checked })}
              />
            )}

            {field.kind === "select" && (
              <select
                className="nodrag h-9 rounded-md border border-input bg-card px-2.5 text-sm text-foreground"
                value={typeof rawValue === "string" ? rawValue : ""}
                onChange={(e) => onConfigChange({ [field.key]: e.target.value })}
              >
                {!field.required && <option value="">--</option>}
                {(field.options ?? []).map((opt) => (
                  <option key={opt} value={opt}>
                    {opt}
                  </option>
                ))}
              </select>
            )}

            {field.kind === "number" && (
              <DraftInput
                type="number"
                value={rawValue === undefined || rawValue === null ? "" : String(rawValue)}
                onCommit={(next) => onConfigChange({ [field.key]: Number(next) || 0 })}
              />
            )}

            {field.kind === "text" && (
              <div className="flex flex-col gap-0.5">
                <DraftInput value={textValue} onCommit={(next) => onConfigChange({ [field.key]: next })} maxLength={field.maxLength} />
                {typeof field.maxLength === "number" && (
                  <span className={`self-end text-[10px] ${nearLimit ? "text-destructive" : "text-muted-foreground"}`}>
                    {charCount}/{field.maxLength}
                  </span>
                )}
                <TemplateHint value={textValue} suggestions={upstreamSuggestions} />
              </div>
            )}

            {field.kind === "textarea" && (
              <div className="flex flex-col gap-0.5">
                <DraftTextarea
                  value={textValue}
                  onCommit={(next) => onConfigChange({ [field.key]: next })}
                  maxLength={field.maxLength}
                />
                {typeof field.maxLength === "number" && (
                  <span className={`self-end text-[10px] ${nearLimit ? "text-destructive" : "text-muted-foreground"}`}>
                    {charCount}/{field.maxLength}
                  </span>
                )}
                <TemplateHint value={textValue} suggestions={upstreamSuggestions} />
              </div>
            )}

            {field.kind === "recipient" &&
              (recipientSuggestion && recipientIsDefault && !recipientExpanded ? (
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[11px] text-muted-foreground">Sending to: the customer who triggered this</p>
                  <button
                    type="button"
                    className="nodrag text-[11px] font-medium text-foreground underline"
                    onClick={() => setExpandedRecipients((prev) => ({ ...prev, [field.key]: true }))}
                  >
                    Send to someone else
                  </button>
                </div>
              ) : (
                <div className="flex flex-col gap-0.5">
                  <DraftInput value={textValue} onCommit={(next) => onConfigChange({ [field.key]: next })} />
                  <TemplateHint value={textValue} suggestions={upstreamSuggestions} />
                </div>
              ))}

            {field.kind === "auto_ref" && (
              <AutoRefFieldRow
                field={field}
                value={textValue}
                onChange={(next) => onConfigChange({ [field.key]: next })}
                upstreamSuggestions={upstreamSuggestions}
                expanded={expandedAutoRefs[field.key] ?? false}
                onToggleExpanded={(next) => setExpandedAutoRefs((prev) => ({ ...prev, [field.key]: next }))}
              />
            )}

            {field.kind === "suggested_select" && (
              <>
                {(field.suggestedOptions ?? []).length === 1 && !expandedSuggestedSelects[field.key] ? (
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-[11px] text-muted-foreground">
                      Connected via: {(field.suggestedOptions ?? [])[0].label}
                    </p>
                    <button
                      type="button"
                      className="nodrag text-[11px] font-medium text-foreground underline"
                      onClick={() => setExpandedSuggestedSelects((prev) => ({ ...prev, [field.key]: true }))}
                    >
                      Change
                    </button>
                  </div>
                ) : (
                  <select
                    className="nodrag h-9 rounded-md border border-input bg-card px-2.5 text-sm text-foreground"
                    value={typeof rawValue === "string" ? rawValue : ""}
                    onChange={(e) => onConfigChange({ [field.key]: e.target.value })}
                  >
                    {!field.required && <option value="">--</option>}
                    {(field.suggestedOptions ?? []).map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                )}
                {(field.suggestedOptions ?? []).length === 0 && field.key === "connector_instance_id" && (
                  <p className="text-[11px] text-muted-foreground">
                    No connected instance yet — connect one in <Link to="/connectors" className="underline">Connectors</Link>
                  </p>
                )}
                {(field.suggestedOptions ?? []).length === 0 && field.key === "module" && (
                  <p className="text-[11px] text-muted-foreground">No modules available.</p>
                )}
              </>
            )}

            {field.kind === "array_text" && (
              <ArrayTextField
                value={rawValue}
                onChange={(next) => onConfigChange({ [field.key]: next })}
                field={field}
                upstreamSuggestions={upstreamSuggestions}
              />
            )}

            {field.kind === "array_object" && (
              <ArrayObjectField
                value={rawValue}
                onChange={(next) => onConfigChange({ [field.key]: next })}
                field={field}
                upstreamSuggestions={upstreamSuggestions}
              />
            )}

            {field.kind === "json_object" && (
              <JsonObjectField
                value={rawValue}
                onChange={(next) => onConfigChange({ [field.key]: next })}
                field={field}
                upstreamSuggestions={upstreamSuggestions}
              />
            )}

            {field.description && <p className="text-[10px] text-muted-foreground">{field.description}</p>}
          </div>
        );
      })}

      {nodeType.node_type === "whatsapp.ask_choice" && (
        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-medium text-muted-foreground">Options</label>
          <AskChoiceSourceField
            value={config.source as AskChoiceSource | undefined}
            onChange={(next) => onConfigChange({ source: next })}
            modules={modules}
          />
        </div>
      )}

      {nodeType.node_type === "whatsapp.send_message" && (
        <div className="flex flex-col gap-1">
          <label className="text-[11px] font-medium text-muted-foreground">Message content</label>
          <SendMessageContentField
            value={config.content as SendMessageContent | undefined}
            onChange={(next) => onConfigChange({ content: next })}
            upstreamSuggestions={upstreamSuggestions}
          />
        </div>
      )}

      {(nodeType.node_type === "records.query" || nodeType.node_type === "records.upsert") && (
        <RecordModuleFields
          nodeType={nodeType.node_type}
          modules={modules}
          config={config}
          onChange={onConfigChange}
          upstreamSuggestions={upstreamSuggestions}
        />
      )}
    </div>
  );
}
