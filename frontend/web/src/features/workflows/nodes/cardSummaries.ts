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
  Megaphone,
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
 * Real per-node-type icons + dynamic output-port derivation for the
 * composable-builder redesign — the pieces that give each node concept a
 * distinct icon (instead of only 3 shared kind badges) and show exactly
 * the output ports a node instance's compiled graph will actually wire
 * (`whatsapp.ask_choice`/`flow.confirm`/`condition.multi_branch`'s
 * config-dependent branches).
 *
 * The one-line config summary this module used to also provide
 * (`summarizeNodeConfig`) was retired once every field rendered inline on
 * the card itself (see `NodeInlineForm.tsx`) - showing a truncated preview
 * above the real, fully-editable field was redundant once that field is
 * always visible, not hidden behind a drawer.
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
  megaphone: Megaphone,
};

/** Left-edge accent + icon-badge colors per `NodeType.palette_group` — the
 * single source of truth imported by both `CardNode.tsx` (per-card accent)
 * and `NodePalette.tsx` (palette row/group accent, via `.border`), so a
 * canvas full of cards and the palette that spawned them are consistently
 * pattern-matchable by category. An unmapped group falls back to
 * `DEFAULT_GROUP_COLOR`, never breaking for a future group this map hasn't
 * caught up with yet. */
export interface GroupColorTokens {
  border: string;
  iconBg: string;
  iconText: string;
}

export const GROUP_COLORS: Record<string, GroupColorTokens> = {
  Triggers: { border: "border-l-red-500", iconBg: "bg-red-100", iconText: "text-red-600" },
  "Talk to Customer": { border: "border-l-emerald-500", iconBg: "bg-emerald-100", iconText: "text-emerald-600" },
  Records: { border: "border-l-blue-500", iconBg: "bg-blue-100", iconText: "text-blue-600" },
  Payments: { border: "border-l-amber-500", iconBg: "bg-amber-100", iconText: "text-amber-600" },
  "Flow Control": { border: "border-l-slate-500", iconBg: "bg-slate-100", iconText: "text-slate-600" },
  Advanced: { border: "border-l-gray-400", iconBg: "bg-gray-100", iconText: "text-gray-600" },
};
export const DEFAULT_GROUP_COLOR: GroupColorTokens = GROUP_COLORS.Advanced;

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
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
