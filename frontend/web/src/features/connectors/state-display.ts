import type { BadgeVariant } from "@fusion-flow/ui";
import {
  Blocks,
  Bot,
  Calendar,
  CreditCard,
  HardDrive,
  Instagram,
  LayoutDashboard,
  Mail,
  MessageCircle,
  Table,
  Video,
  type LucideIcon,
} from "lucide-react";
import type { ConnectorCategory, ConnectorHealthStatus, ConnectorState } from "./types";

/** State -> badge variant/label. One source of truth for `ConnectorCard` + `ConnectorDetailPage`. */
export const CONNECTOR_STATE_DISPLAY: Record<ConnectorState, { label: string; variant: BadgeVariant }> = {
  not_connected: { label: "Not connected", variant: "outline" },
  connecting: { label: "Connecting…", variant: "secondary" },
  connected: { label: "Connected", variant: "success" },
  action_required: { label: "Action required", variant: "default" },
  error: { label: "Error", variant: "destructive" },
  disconnected: { label: "Disconnected", variant: "outline" },
};

export const CONNECTOR_HEALTH_DISPLAY: Record<ConnectorHealthStatus, { label: string; variant: BadgeVariant }> = {
  healthy: { label: "Healthy", variant: "success" },
  degraded: { label: "Degraded", variant: "default" },
  down: { label: "Down", variant: "destructive" },
};

export const CONNECTOR_CATEGORY_ICON: Record<ConnectorCategory, LucideIcon> = {
  messaging: MessageCircle,
  payment: CreditCard,
  calendar: Calendar,
  mail: Mail,
  support_agent: Bot,
  dashboard: LayoutDashboard,
  feature: Blocks,
  storage: HardDrive,
  social: Instagram,
  video: Video,
  spreadsheet: Table,
};

/** Whether the "Connect"/"Reconnect" CTA should be offered for this state. */
export function isReconnectable(state: ConnectorState | undefined): boolean {
  return (
    state === undefined ||
    state === "not_connected" ||
    state === "error" ||
    state === "action_required" ||
    state === "disconnected"
  );
}

export function formatRelativeTimestamp(iso: string | null | undefined): string {
  if (!iso) return "Never";
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const diffMinutes = Math.round(diffMs / 60_000);
  if (diffMinutes < 1) return "Just now";
  if (diffMinutes < 60) return `${diffMinutes}m ago`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays}d ago`;
}
