import {
  Bell,
  BookOpen,
  Calendar,
  CheckCircle,
  CreditCard,
  Database,
  FilePlus,
  Gift,
  Globe,
  LifeBuoy,
  ListChecks,
  MessageCircle,
  MessageSquareText,
  Package,
  ShoppingCart,
  Star,
  TicketPercent,
  Users,
  Wrench,
  type LucideIcon,
} from "lucide-react";

/**
 * Human-readable card summaries + real per-node-type icons + dynamic
 * output-port derivation for the composable-builder redesign — the pieces
 * that make `CardNode.tsx` show "Ask: 'Would you like fries?' (2 options)"
 * instead of a raw `question: Would you like fries?` config line, and a
 * distinct icon per node concept instead of only 3 shared kind badges.
 *
 * Kept as its own module (not inlined into `CardNode.tsx`) so the ~7
 * bespoke-summary node types don't clutter the component itself, and so
 * `deriveOutputHandles`'s dispatch table sits next to the summaries it's
 * conceptually paired with.
 */

/** kebab-case `icon` key (matches this codebase's `WorkflowNodeTemplate`/
 * `FIXED_MODULE_CATALOG`/`NodeExecutor.icon` string convention) -> the
 * matching `lucide-react` component. An unrecognized or absent key falls
 * back to `CardNode`'s existing kind-based badge (Zap/PlayCircle/
 * GitBranch) - this map is purely additive, never a hard requirement. */
export const NODE_ICONS: Record<string, LucideIcon> = {
  package: Package,
  wrench: Wrench,
  "ticket-percent": TicketPercent,
  gift: Gift,
  users: Users,
  "life-buoy": LifeBuoy,
  "book-open": BookOpen,
  "shopping-cart": ShoppingCart,
  "credit-card": CreditCard,
  database: Database,
  "file-plus": FilePlus,
  "list-checks": ListChecks,
  "message-square-text": MessageSquareText,
  "message-circle": MessageCircle,
  "check-circle": CheckCircle,
  globe: Globe,
  bell: Bell,
  star: Star,
  calendar: Calendar,
};

export type ConnectorInstanceLabelFn = (connectorInstanceId: string) => string | undefined;

function resolveConnectorLabel(
  config: Record<string, unknown>,
  key: string,
  connectorInstanceLabel?: ConnectorInstanceLabelFn,
): string | undefined {
  const raw = config[key];
  if (typeof raw !== "string" || !raw) return undefined;
  return connectorInstanceLabel?.(raw) ?? raw;
}

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

/** One-line, human-readable summary of a node's current config, for the
 * ~7 new composite node types this redesign introduces. Returns `null`
 * for every other (pre-existing) node type - `CardNode.tsx` falls back to
 * its own existing raw key:value preview in that case, so none of the
 * other ~60 node types change behavior. Never throws - a config shape
 * this function doesn't expect just falls through to `null` rather than
 * crashing the canvas (`CardNode.tsx` wraps the call in try/catch too, as
 * a second line of defense). */
export function summarizeNodeConfig(
  nodeType: string,
  config: Record<string, unknown>,
  connectorInstanceLabel?: ConnectorInstanceLabelFn,
): string | null {
  switch (nodeType) {
    case "whatsapp.ask_choice": {
      const question = asString(config.question);
      const source = config.source as { kind?: string; options?: { id?: string }[]; module?: string } | undefined;
      const countLabel =
        source?.kind === "static"
          ? `${source.options?.length ?? 0} option${(source.options?.length ?? 0) === 1 ? "" : "s"}`
          : source?.kind === "module"
            ? `from ${source.module || "a module"}`
            : "no options yet";
      const channel = resolveConnectorLabel(config, "connector_instance_id", connectorInstanceLabel);
      return `Ask${channel ? ` (${channel})` : ""}: "${question}" (${countLabel})`;
    }
    case "flow.confirm": {
      const question = asString(config.question);
      const channel = resolveConnectorLabel(config, "connector_instance_id", connectorInstanceLabel);
      return `Confirm${channel ? ` (${channel})` : ""}: "${question}"`;
    }
    case "whatsapp.collect_text": {
      const question = asString(config.question);
      const channel = resolveConnectorLabel(config, "connector_instance_id", connectorInstanceLabel);
      return `Collect a reply${channel ? ` (${channel})` : ""} to: "${question}"`;
    }
    case "records.query":
    case "records.upsert": {
      const operation = asString(config.operation, "?");
      const module = asString(config.module, "a");
      const verb = operation ? operation.charAt(0).toUpperCase() + operation.slice(1) : "?";
      return `${verb} ${module} record${operation === "list" ? "s" : ""}`;
    }
    case "payments.send_razorpay_link": {
      const amount = config.amount;
      const currency = asString(config.currency, "INR");
      const channel = resolveConnectorLabel(config, "whatsapp_connector_instance_id", connectorInstanceLabel);
      const amountLabel = amount === undefined || amount === null || amount === "" ? "?" : String(amount);
      return `Send a payment link${channel ? ` via ${channel}` : ""} for ${amountLabel} ${currency}`;
    }
    default:
      return null;
  }
}

/** Which output ports a node instance should show, given its own config -
 * mirrors the backend's own derivation rules 1:1 (see
 * `engine/composite_branching.py` for `whatsapp.ask_choice`/`flow.confirm`,
 * `nodes/condition_multi_branch.py` for the dynamic-handle case) so the
 * canvas shows exactly the ports the compiled graph will actually wire -
 * kept as a small, duplicated, deliberately trivial rule on each side
 * rather than a round-trip to the backend for a preview, per the plan's
 * "client-side duplication, revisit only if it drifts" decision.
 *
 * `staticHandles` is `meta?.output_handles` - the palette metadata's own
 * (static, per-node-*type*) handle list, used unchanged for every node
 * type not listed below (including a module-sourced `whatsapp.ask_choice`,
 * which has no compile-time branch and is just a single-successor
 * suspending action, same as `whatsapp.ask_question` today). */
export function deriveOutputHandles(
  nodeType: string,
  config: Record<string, unknown>,
  staticHandles: string[] | null,
): string[] | null {
  switch (nodeType) {
    case "condition.multi_branch": {
      const cases = Array.isArray(config.cases) ? (config.cases as { label?: unknown }[]) : [];
      const labels = cases.map((c) => asString(c.label)).filter(Boolean);
      const defaultLabel = asString(config.default_label, "default");
      return [...labels, defaultLabel];
    }
    case "whatsapp.ask_choice": {
      const source = config.source as { kind?: string; options?: { id?: unknown }[] } | undefined;
      if (source?.kind === "static") {
        return (source.options ?? []).map((o) => asString(o.id)).filter(Boolean);
      }
      return staticHandles;
    }
    case "flow.confirm":
      return ["yes", "no"];
    default:
      return staticHandles;
  }
}
