import type { ReactNode } from "react";
import { Clock, Lock } from "lucide-react";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { useCanManageAccess, useModuleAccess } from "../../lib/useModuleAccess";
import { getApiErrorDetail } from "../../lib/access-events";
import { useConnectorTypes, useRequestConnectorAccess } from "../../features/connectors/hooks";

/**
 * Guards a fixed-module route (products, tickets, ...) behind the tenant's
 * entitlement, mirroring `RequireAuth`'s simplicity. Backed by
 * `useModuleAccess()`, which reads the same generic `access_status` the
 * Connectors grid already uses - no separate backend endpoint needed.
 */
export function RequireModule({ moduleKey, children }: { moduleKey: string; children: ReactNode }) {
  const { map, isLoading } = useModuleAccess();
  if (isLoading) {
    return <div className="p-8 text-center text-sm text-muted-foreground">Loading…</div>;
  }
  const status = map[moduleKey] ?? "not_requested";
  if (status !== "granted") {
    return <ModuleAccessRequiredPage moduleKey={moduleKey} status={status} />;
  }
  return <>{children}</>;
}

const ROLE_LABEL: Record<string, string> = { owner: "Owner", admin: "Admin", member: "Member", viewer: "Viewer" };

function ModuleAccessRequiredPage({
  moduleKey,
  status,
}: {
  moduleKey: string;
  status: "pending" | "denied" | "restricted" | "not_requested" | "granted";
}) {
  const requestAccessMutation = useRequestConnectorAccess();
  const { data: types } = useConnectorTypes();
  const { role, canManage } = useCanManageAccess();

  const type = types?.find((t) => t.key === moduleKey);
  const name = type?.display_name ?? moduleKey;
  const nameByKey = new Map((types ?? []).map((t) => [t.key, t.display_name]));
  // Features that stop working here too - shown so a revoked module isn't a
  // mystery when e.g. the Customer picker on Orders disappears.
  const affected = (type?.dependents ?? []).map((k) => nameByKey.get(k) ?? k);
  const roleLabel = role ? (ROLE_LABEL[role] ?? role) : "your role";

  const Icon = status === "pending" ? Clock : Lock;
  const title =
    status === "pending"
      ? `${name} - awaiting approval`
      : status === "denied"
        ? `${name} access was revoked`
        : status === "restricted"
          ? `${name} is restricted for your role`
          : `${name} isn't enabled yet`;

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-16 text-center">
      <Card className="w-full">
        <CardHeader className="items-center">
          <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-muted">
            <Icon className="h-5 w-5 text-muted-foreground" />
          </div>
          <CardTitle>{title}</CardTitle>
          <CardDescription>
            {status === "pending" &&
              "Your request for this module is pending platform approval. You'll get access here as soon as it's approved - no action needed."}
            {status === "denied" &&
              "Access to this module was revoked or denied by the platform administrator. Anything that relies on it (including workflows) is paused. Contact FusionFlow support to have it restored."}
            {status === "restricted" &&
              `An Owner or Admin of your business has turned this module off for the ${roleLabel} role. Ask your business Owner or Admin to enable it for you.`}
            {status === "not_requested" &&
              (canManage
                ? "Your business doesn't have this module yet. Request access and the platform team will review it."
                : "Your business doesn't have this module yet. Ask your business Owner or Admin to request it.")}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col items-center gap-3">
          {status === "restricted" && role && <Badge variant="outline">Your role: {roleLabel}</Badge>}
          {status === "denied" && affected.length > 0 && (
            <p className="text-xs text-muted-foreground">
              Also affected: {affected.join(", ")} features that use {name}.
            </p>
          )}
          {status === "not_requested" && canManage && !requestAccessMutation.isSuccess && (
            <Button
              onClick={() => requestAccessMutation.mutate({ typeKey: moduleKey })}
              disabled={requestAccessMutation.isPending}
            >
              {requestAccessMutation.isPending ? "Requesting…" : "Request access"}
            </Button>
          )}
          {requestAccessMutation.isSuccess && (
            <p className="text-sm text-muted-foreground">Request sent - pending admin approval.</p>
          )}
          {requestAccessMutation.isError && (
            <p className="text-sm text-destructive">
              {getApiErrorDetail(requestAccessMutation.error, "Could not send the request. Please try again.")}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
