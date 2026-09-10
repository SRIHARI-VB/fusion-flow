import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { CheckCircle2, RefreshCw, Unplug } from "lucide-react";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, cn } from "@fusion-flow/ui";
import { ConnectorEventsTable } from "../components/ConnectorEventsTable";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { useConnectorEvents, useConnectorInstances, useDisconnectConnector, useTestConnector } from "../hooks";
import { CONNECTOR_HEALTH_DISPLAY, CONNECTOR_STATE_DISPLAY, formatRelativeTimestamp } from "../state-display";
import { CONNECTOR_SETTINGS } from "../settings/registry";

type Tab = "activity" | "settings";

/**
 * `/connectors/:instanceId` - generic detail page for any connector
 * instance: identity (adapter-redacted allowlist only), event history,
 * and the same test/disconnect actions the grid card offers, plus a
 * per-connector-type "Settings" tab (Part F's registry - see
 * `../settings/registry.ts`) for anything beyond the generic lifecycle
 * surface (e.g. WhatsApp's message template catalog). A connector with
 * nothing registered there gets a plain fallback message - purely
 * additive, no change for connectors without a settings panel.
 */
export function ConnectorDetailPage() {
  const { instanceId } = useParams<{ instanceId: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const justConnected = searchParams.get("connected") === "1";

  const { data: instances, isLoading } = useConnectorInstances();
  const { data: events, isLoading: eventsLoading } = useConnectorEvents(instanceId);
  const testMutation = useTestConnector();
  const disconnectMutation = useDisconnectConnector();
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false);
  const [tab, setTab] = useState<Tab>("activity");

  const instance = instances?.find((candidate) => candidate.id === instanceId);

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading connector…</p>;
  }

  if (!instance) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Connector not found</CardTitle>
          <CardDescription>This connector instance doesn't exist, or belongs to a different business.</CardDescription>
        </CardHeader>
      </Card>
    );
  }

  const stateDisplay = CONNECTOR_STATE_DISPLAY[instance.state];
  const healthDisplay = instance.health_status ? CONNECTOR_HEALTH_DISPLAY[instance.health_status] : null;
  const identityEntries = Object.entries(instance.connected_identity ?? {});

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">{instance.display_name}</h1>
          <p className="text-sm text-muted-foreground">{instance.connector_type_display_name}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={stateDisplay.variant}>{stateDisplay.label}</Badge>
          {healthDisplay && <Badge variant={healthDisplay.variant}>{healthDisplay.label}</Badge>}
        </div>
      </div>

      {justConnected && (
        <div className="flex items-center gap-2 rounded-md border border-success/30 bg-success-soft px-4 py-3 text-sm text-success">
          <CheckCircle2 className="h-4 w-4" />
          Connected successfully.
        </div>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Connected identity</CardTitle>
          <CardDescription>
            Only the safe fields the provider adapter allowlisted - never a raw credential.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {identityEntries.length > 0 ? (
            <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {identityEntries.map(([key, value]) => (
                <div key={key} className="flex flex-col">
                  <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                    {key.replace(/_/g, " ")}
                  </dt>
                  <dd className="text-sm text-foreground">{String(value)}</dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">Not connected yet.</p>
          )}
        </CardContent>
      </Card>

      <div className="flex gap-1 border-b border-border">
        {(["activity", "settings"] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={cn(
              "border-b-2 px-3 py-2 text-sm font-medium capitalize",
              tab === t ? "border-accent text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
            onClick={() => setTab(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === "activity" && (
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Activity</CardTitle>
              <CardDescription>
                Last webhook: {formatRelativeTimestamp(instance.last_webhook_at)} · Last sync:{" "}
                {formatRelativeTimestamp(instance.last_sync_at)}
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => testMutation.mutate(instance.id)}
                disabled={testMutation.isPending}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                {testMutation.isPending ? "Testing…" : "Test connection"}
              </Button>
              <Button variant="destructive" size="sm" onClick={() => setConfirmingDisconnect(true)}>
                <Unplug className="h-3.5 w-3.5" />
                Disconnect
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <ConnectorEventsTable events={events ?? []} isLoading={eventsLoading} />
          </CardContent>
        </Card>
      )}

      {tab === "settings" &&
        (() => {
          const SettingsPanel = CONNECTOR_SETTINGS[instance.connector_type_key];
          return SettingsPanel ? (
            <SettingsPanel instance={instance} />
          ) : (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                No additional settings for this connector.
              </CardContent>
            </Card>
          );
        })()}

      <ConfirmDialog
        open={confirmingDisconnect}
        title={`Disconnect ${instance.display_name}?`}
        description="Workflows depending on this connector will stop firing until it's reconnected. Its history is retained for support."
        confirmLabel="Disconnect"
        destructive
        busy={disconnectMutation.isPending}
        onCancel={() => setConfirmingDisconnect(false)}
        onConfirm={() =>
          disconnectMutation.mutate(instance.id, {
            onSuccess: () => {
              setConfirmingDisconnect(false);
              navigate("/connectors");
            },
          })
        }
      />
    </div>
  );
}
