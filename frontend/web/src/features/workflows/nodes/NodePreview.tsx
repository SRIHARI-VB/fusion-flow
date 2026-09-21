import { cn } from "@fusion-flow/ui";
import type { NodeType } from "../types";
import type { SendMessageButton, SendMessageContent, SendMessageListSection } from "../components/SendMessageContentField";
import type { AskChoiceSource } from "../components/AskChoiceSourceField";
import { LocationPreview, MediaThumb, isUnsetLocation, type MediaKind } from "../components/MediaPreview";

/**
 * The collapsed-card presentation layer for the "collapse by default, click
 * to expand" redesign (see `CardNode.tsx`/`ContainerNode.tsx`). Two
 * renderers, chosen by `isChatPreview`:
 *
 * - `MessageBubblePreview` - a small WhatsApp-style chat-bubble mockup for
 *   the "Talk to Customer" node family (send/ask/confirm), the same
 *   collapsed representation ManyChat/Wati/AiSensy use for their own
 *   message-composing blocks - the whole point of collapsing one of these
 *   is to *also* show what the customer will see, not just save space.
 * - `NodeSummaryLine` - a one-line human-readable summary for every other
 *   node type (conditions, records, integrations, flow control, ...),
 *   the same job the deleted `cardSummaries.ts::summarizeNodeConfig` used
 *   to do before the "everything inline, always" redesign retired it -
 *   reintroduced here because collapsing the card is exactly the case
 *   that justifies it again.
 *
 * Both are read-only: neither takes an `onChange` - editing only ever
 * happens in the expanded `NodeInlineForm` this replaces while collapsed.
 */

/** Every node type in the "Talk to Customer" palette group composes a
 * WhatsApp message of some kind - reuses the same `palette_group` the
 * palette/card-accent-color already key off (`cardSummaries.ts`'s
 * `GROUP_COLORS`), rather than hardcoding a second parallel list of node
 * type strings. */
export function isChatPreview(meta: NodeType | undefined): boolean {
  return meta?.palette_group === "Talk to Customer";
}

interface BubbleModel {
  body: string;
  buttons?: string[];
  listRows?: string[];
  footer?: string;
  media?: { mediaType: MediaKind; url?: string; mediaId?: string; filename?: string };
  location?: { latitude: number; longitude: number; name?: string; address?: string };
}

const MAX_PREVIEW_ROWS = 4;

function truncateRows(rows: string[]): string[] {
  if (rows.length <= MAX_PREVIEW_ROWS) return rows;
  return [...rows.slice(0, MAX_PREVIEW_ROWS), `+${rows.length - MAX_PREVIEW_ROWS} more`];
}

function sendMessageBubble(content: SendMessageContent | undefined): BubbleModel {
  if (!content) return { body: "" };
  switch (content.content_type) {
    case "text":
      return { body: content.body ?? "" };
    case "media":
      return {
        body: content.caption ?? "",
        media: { mediaType: content.media_type, url: content.media_url, mediaId: content.media_id, filename: content.filename },
      };
    case "location":
      return isUnsetLocation(content.latitude, content.longitude)
        ? { body: "" }
        : { body: "", location: { latitude: content.latitude, longitude: content.longitude, name: content.name, address: content.address } };
    case "contact": {
      const names = (content.contacts ?? []).map((c) => c.name).filter(Boolean);
      return { body: names.length > 0 ? `Contact: ${names.join(", ")}` : "Contact card" };
    }
    case "template":
      return {
        body: content.template_name ? `Template: ${content.template_name}` : "Template message",
        footer: content.language_code,
        media:
          content.header_media_url || content.header_media_id
            ? { mediaType: content.header_media_type ?? "image", url: content.header_media_url, mediaId: content.header_media_id }
            : undefined,
      };
    case "buttons":
      return {
        body: content.body_text ?? "",
        buttons: (content.buttons ?? []).map((b: SendMessageButton) => b.title).filter(Boolean),
      };
    case "list":
      return {
        body: content.body_text ?? "",
        listRows: (content.sections ?? []).flatMap((s: SendMessageListSection) => s.rows.map((r) => r.title)).filter(Boolean),
      };
    default:
      return { body: "" };
  }
}

function askChoiceBubble(question: string, source: AskChoiceSource | undefined): BubbleModel {
  if (!source || source.kind !== "static") {
    const moduleName = source && source.kind === "module" ? source.module : "";
    return { body: question, footer: moduleName ? `Options from: ${moduleName}` : "Options from a module" };
  }
  const labels = source.options.map((o) => o.label).filter(Boolean);
  // Mirrors WhatsApp's own render rule (see `AskChoiceSourceField.tsx`):
  // up to 3 options show as quick-reply buttons, more than that as a list.
  return labels.length <= 3 ? { body: question, buttons: labels } : { body: question, listRows: labels };
}

function buildBubbleModel(nodeType: string, config: Record<string, unknown>): BubbleModel {
  switch (nodeType) {
    case "whatsapp.send_message":
      return sendMessageBubble(config.content as SendMessageContent | undefined);
    case "whatsapp.ask_question": {
      const question = typeof config.question === "string" ? config.question : "";
      if (config.input_type === "buttons") {
        const buttons = (config.buttons as { title?: unknown }[] | undefined) ?? [];
        return { body: question, buttons: buttons.map((b) => String(b.title ?? "")).filter(Boolean) };
      }
      if (config.input_type === "list") {
        const sections = (config.sections as { rows?: { title?: unknown }[] }[] | undefined) ?? [];
        const rows = sections.flatMap((s) => (s.rows ?? []).map((r) => String(r.title ?? ""))).filter(Boolean);
        return { body: question, listRows: rows };
      }
      return { body: question };
    }
    case "whatsapp.ask_choice":
      return askChoiceBubble(String(config.question ?? ""), config.source as AskChoiceSource | undefined);
    case "whatsapp.collect_text":
      return { body: String(config.question ?? "") };
    case "whatsapp.ask_via_template":
      return {
        body: config.template_name ? `Template: ${config.template_name}` : "",
        footer: typeof config.language_code === "string" ? config.language_code : undefined,
      };
    case "whatsapp.ask_for_cart":
      return {
        body: String(config.body_text ?? ""),
        footer: config.section_title ? `Product picker: ${config.section_title}` : "Product picker",
      };
    case "flow.confirm":
      return { body: String(config.question ?? ""), buttons: ["Yes", "No"] };
    default:
      return { body: "" };
  }
}

export function MessageBubblePreview({ nodeType, config }: { nodeType: string; config: Record<string, unknown> }) {
  const model = buildBubbleModel(nodeType, config);
  const rows = model.listRows ? truncateRows(model.listRows) : undefined;

  if (!model.body && !model.buttons?.length && !rows?.length && !model.media && !model.location) {
    return <p className="text-xs italic text-muted-foreground">Tap to write this message...</p>;
  }

  return (
    <div className="flex flex-col gap-1">
      <div className="max-w-full rounded-lg rounded-tl-none bg-[#dcf8c6] px-2.5 py-1.5 text-xs text-foreground shadow-sm">
        {model.media && (
          <div className="mb-1">
            <MediaThumb
              mediaType={model.media.mediaType}
              url={model.media.url}
              mediaId={model.media.mediaId}
              filename={model.media.filename}
              size="sm"
            />
          </div>
        )}
        {model.location && (
          <div className="mb-1">
            <LocationPreview
              latitude={model.location.latitude}
              longitude={model.location.longitude}
              name={model.location.name}
              address={model.location.address}
              size="sm"
            />
          </div>
        )}
        {model.body ? (
          <p className="whitespace-pre-wrap break-words">{model.body}</p>
        ) : (
          !model.media && !model.location && <p className="italic text-muted-foreground">(empty)</p>
        )}
        {model.footer && <p className="mt-0.5 text-[10px] text-muted-foreground">{model.footer}</p>}
      </div>
      {model.buttons && model.buttons.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {model.buttons.map((label, i) => (
            <span key={i} className="rounded-md border border-border bg-card px-2 py-1 text-center text-[11px] text-primary">
              {label}
            </span>
          ))}
        </div>
      )}
      {rows && rows.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {rows.map((label, i) => (
            <span key={i} className="rounded-md border border-border bg-card px-2 py-1 text-[11px] text-foreground">
              {label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

const OPERATOR_LABELS: Record<string, string> = {
  eq: "equals",
  neq: "not equals",
  gt: "greater than",
  gte: "greater than or equal",
  lt: "less than",
  lte: "less than or equal",
  contains: "contains",
};

function short(value: unknown, max = 40): string {
  const text = typeof value === "string" ? value : value == null ? "" : JSON.stringify(value);
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

/** One-line, best-effort human summary for every node type that isn't a
 * chat-preview candidate (see `isChatPreview`) - a node type not covered
 * below (including every trigger, which has no meaningful config to
 * summarize) simply renders nothing, leaving the header + description as
 * the collapsed view. */
export function summarizeNodeConfig(nodeType: string, config: Record<string, unknown>): string | null {
  switch (nodeType) {
    case "condition.field_compare": {
      const op = OPERATOR_LABELS[String(config.operator)] ?? String(config.operator ?? "equals");
      return `If ${short(config.field_path, 24)} ${op} ${short(config.value, 20)}`;
    }
    case "condition.multi_branch": {
      const cases = Array.isArray(config.cases) ? config.cases : [];
      return `${cases.length} branch${cases.length === 1 ? "" : "es"}, else default`;
    }
    case "records.query": {
      const op = config.operation === "get" ? "Get one" : "List";
      return config.module ? `${op} from ${config.module}` : `${op} records`;
    }
    case "records.upsert": {
      const op = config.operation === "update" ? "Update" : "Create";
      return config.module ? `${op} a ${config.module} record` : `${op} a record`;
    }
    case "module.list":
      return config.module ? `List ${config.module}` : "List records";
    case "module.get":
      return config.module ? `Get one ${config.module}` : "Get a record";
    case "module.create":
      return config.module ? `Create a ${config.module} record` : "Create a record";
    case "module.update":
      return config.module ? `Update a ${config.module} record` : "Update a record";
    case "http.request":
      return `${config.method ?? "GET"} ${short(config.url, 36)}`;
    case "connector.action":
      return config.action ? `Run "${short(config.action, 30)}"` : "Run a connector action";
    case "flow.loop":
      return `For each item in ${short(config.items_path, 30)}`;
    case "flow.parallel":
      return `Run branches in parallel (wait for: ${config.wait_for ?? "all"})`;
    case "create_ticket":
      return `Create ticket: ${short(config.subject, 30)}`;
    case "payments.send_razorpay_link":
      return `Send payment link${config.amount ? ` for ${short(config.amount, 16)} ${config.currency ?? ""}` : ""}`;
    case "orders.create_from_cart":
    case "orders.create_from_conversation":
      return `Create order (${config.payment_method === "prepaid" ? "prepaid" : "cash on delivery"})`;
    case "whatsapp.mark_as_read":
      return "Mark the message as read";
    case "whatsapp.get_business_profile":
      return "Get the WhatsApp business profile";
    case "whatsapp.update_business_profile":
      return "Update the WhatsApp business profile";
    case "whatsapp.find_or_create_customer":
      return config.phone ? `Find or create customer ${short(config.phone, 20)}` : "Find or create a customer";
    case "data.transform":
      return `Compute ${Object.keys((config.outputs as object) ?? {}).length} value(s)`;
    default:
      return null;
  }
}

export function NodeSummaryLine({ nodeType, config }: { nodeType: string; config: Record<string, unknown> }) {
  const text = summarizeNodeConfig(nodeType, config);
  if (!text) return null;
  return <p className="truncate text-xs text-muted-foreground">{text}</p>;
}

export function CollapsedPreview({ meta, nodeType, config }: { meta: NodeType | undefined; nodeType: string; config: Record<string, unknown> }) {
  if (isChatPreview(meta)) return <MessageBubblePreview nodeType={nodeType} config={config} />;
  return <NodeSummaryLine nodeType={nodeType} config={config} />;
}

export const collapsedPreviewRowClass = cn("nodrag flex w-full cursor-pointer flex-col gap-1 rounded-md px-1 py-0.5 text-left hover:bg-muted/60");
