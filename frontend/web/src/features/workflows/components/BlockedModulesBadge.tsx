import { AlertTriangle } from "lucide-react";
import { Badge } from "@fusion-flow/ui";
import type { BlockedModule } from "../types";

const REASON_TEXT: Record<BlockedModule["reason"], string> = {
  denied: "access was revoked",
  not_requested: "isn't enabled for your business",
  pending: "is awaiting approval",
};

/** One-sentence explanation, reused as the badge tooltip and the editor banner. */
export function describeBlockedModules(blocked: BlockedModule[]): string {
  const parts = blocked.map((m) => `${m.display_name} (${REASON_TEXT[m.reason]})`);
  return `This workflow uses modules you can't currently access: ${parts.join(", ")}. It won't run until access is restored.`;
}

/** Warning badge for a workflow whose graph uses modules the tenant can't access; renders nothing otherwise. */
export function BlockedModulesBadge({ blocked }: { blocked?: BlockedModule[] }) {
  if (!blocked || blocked.length === 0) return null;
  return (
    <Badge
      variant="destructive"
      title={describeBlockedModules(blocked)}
      className="gap-1 bg-amber-100 text-amber-800 border-transparent"
    >
      <AlertTriangle className="h-3 w-3" />
      Blocked: {blocked.map((m) => m.display_name).join(", ")}
    </Badge>
  );
}
