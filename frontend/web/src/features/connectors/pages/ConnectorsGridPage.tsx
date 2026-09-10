import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import { Card, CardDescription, CardHeader, CardTitle } from "@fusion-flow/ui";
import { ConnectorCard } from "../components/ConnectorCard";
import { ConfirmDialog } from "../components/ConfirmDialog";
import {
  useConnectorInstances,
  useConnectorTypes,
  useDisconnectConnector,
  useRequestConnectorAccess,
  useTestConnector,
} from "../hooks";

/**
 * `/connectors` - grid of every catalog type, each paired with the
 * tenant's own instance (if any). Types with no matching instance render
 * as "Not connected" with a Connect CTA, per the plan's frontend routes.
 */
export function ConnectorsGridPage() {
  const { data: allTypes, isLoading: typesLoading } = useConnectorTypes();
  // External integrations only - fixed feature modules (category "feature")
  // are surfaced through nav + a "request access" page instead (see
  // useModuleAccess/RequireModule), not through this Connect/Request-access
  // grid, since "connecting" a feature module has no meaning.
  const types = (allTypes ?? []).filter((t) => t.category !== "feature");
  const { data: instances, isLoading: instancesLoading } = useConnectorInstances();
  const testMutation = useTestConnector();
  const disconnectMutation = useDisconnectConnector();
  const requestAccessMutation = useRequestConnectorAccess();
  const [pendingDisconnectId, setPendingDisconnectId] = useState<string | null>(null);

  const instanceByTypeId = new Map((instances ?? []).map((instance) => [instance.connector_type_id, instance]));
  const pendingInstance = (instances ?? []).find((instance) => instance.id === pendingDisconnectId);

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Connectors</h1>
        <p className="text-sm text-muted-foreground">
          Connect messaging, payment and other providers. Every connector follows the same
          connect → connected → test / disconnect lifecycle.
        </p>
      </div>

      {typesLoading || instancesLoading ? (
        <p className="text-sm text-muted-foreground">Loading connectors…</p>
      ) : types.length === 0 ? (
        <Card>
          <CardHeader className="items-center text-center">
            <AlertTriangle className="mb-2 h-6 w-6 text-muted-foreground" />
            <CardTitle>No connector types available</CardTitle>
            <CardDescription>The connector catalog is empty right now - check back later.</CardDescription>
          </CardHeader>
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {types.map((type) => (
            <ConnectorCard
              key={type.id}
              connectorType={type}
              instance={instanceByTypeId.get(type.id)}
              onTest={(instanceId) => testMutation.mutate(instanceId)}
              onDisconnect={(instanceId) => setPendingDisconnectId(instanceId)}
              onRequestAccess={(typeKey) => requestAccessMutation.mutate({ typeKey })}
              testBusy={testMutation.isPending}
              requestAccessBusy={requestAccessMutation.isPending}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={pendingDisconnectId !== null}
        title={`Disconnect ${pendingInstance?.display_name ?? "this connector"}?`}
        description="Workflows depending on this connector will stop firing until it's reconnected. Its history is retained for support."
        confirmLabel="Disconnect"
        destructive
        busy={disconnectMutation.isPending}
        onCancel={() => setPendingDisconnectId(null)}
        onConfirm={() => {
          if (!pendingDisconnectId) return;
          disconnectMutation.mutate(pendingDisconnectId, {
            onSettled: () => setPendingDisconnectId(null),
          });
        }}
      />
    </div>
  );
}
