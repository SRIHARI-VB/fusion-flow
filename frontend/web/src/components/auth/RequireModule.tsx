import type { ReactNode } from "react";
import { Lock } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { useModuleAccess } from "../../lib/useModuleAccess";
import { useRequestConnectorAccess } from "../../features/connectors/hooks";

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

function ModuleAccessRequiredPage({
  moduleKey,
  status,
}: {
  moduleKey: string;
  status: "pending" | "denied" | "not_requested";
}) {
  const requestAccessMutation = useRequestConnectorAccess();

  return (
    <div className="mx-auto flex max-w-md flex-col items-center gap-4 py-16 text-center">
      <Card className="w-full">
        <CardHeader className="items-center">
          <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-muted">
            <Lock className="h-5 w-5 text-muted-foreground" />
          </div>
          <CardTitle>Module not available</CardTitle>
          <CardDescription>
            {status === "pending" && "Your request for this module is pending admin approval."}
            {status === "denied" && "Access to this module was denied by an administrator."}
            {status === "not_requested" &&
              "Your business does not have access to this module yet. Request it from an administrator."}
          </CardDescription>
        </CardHeader>
        {status === "not_requested" && (
          <CardContent className="flex justify-center">
            <Button
              onClick={() => requestAccessMutation.mutate({ typeKey: moduleKey })}
              disabled={requestAccessMutation.isPending}
            >
              {requestAccessMutation.isPending ? "Requesting…" : "Request access"}
            </Button>
          </CardContent>
        )}
        {requestAccessMutation.isSuccess && (
          <CardContent>
            <p className="text-sm text-muted-foreground">Request sent - pending admin approval.</p>
          </CardContent>
        )}
      </Card>
    </div>
  );
}
