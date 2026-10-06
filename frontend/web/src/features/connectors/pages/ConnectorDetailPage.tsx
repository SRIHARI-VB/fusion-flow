import { useCanManageAccess } from "../../../lib/useModuleAccess";
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Check, CheckCircle2, Copy, RefreshCw, Unplug } from "lucide-react";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, cn } from "@fusion-flow/ui";
import { ConnectorEventsTable } from "../components/ConnectorEventsTable";
import { ConfirmDialog } from "../components/ConfirmDialog";
import {
  useConnectorEvents,
  useConnectorInstances,
  useConnectorTypes,
  useDisconnectConnector,
  useTestConnector,
} from "../hooks";
import { CONNECTOR_HEALTH_DISPLAY, CONNECTOR_STATE_DISPLAY, formatRelativeTimestamp } from "../state-display";
import { CONNECTOR_SETTINGS } from "../settings/registry";
import { useSetPageTitle } from "../../../components/layout/page-title";

type Tab = "activity" | "settings";

/** A read-only value with a copy-to-clipboard button - used for the
 * webhook callback URL/verify token, which a tenant needs to paste
 * verbatim into Meta's dashboard. */
function CopyableField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
      <div className="flex items-center gap-2">
        <code className="flex-1 truncate rounded-md border border-border bg-muted px-2.5 py-1.5 text-xs text-foreground">
          {value}
        </code>
        <Button type="button" variant="outline" size="sm" onClick={handleCopy}>
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
    </div>
  );
}

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
  const { data: connectorTypes } = useConnectorTypes();
  const { data: events, isLoading: eventsLoading } = useConnectorEvents(instanceId);
  const { canManage } = useCanManageAccess();
  const manageHint = canManage ? undefined : "Only an Owner or Admin can manage connectors.";
  const testMutation = useTestConnector();
  const disconnectMutation = useDisconnectConnector();
  const [confirmingDisconnect, setConfirmingDisconnect] = useState(false);
  const [tab, setTab] = useState<Tab>("activity");

  const instance = instances?.find((candidate) => candidate.id === instanceId);
  useSetPageTitle(instance?.display_name ?? null);

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
  const connectorType = connectorTypes?.find((t) => t.key === instance.connector_type_key);
  const needsWebhookSetup = instance.state === "connected" && !!connectorType?.webhook_callback_url;

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

      {needsWebhookSetup && connectorType && (
        <Card>
          <CardHeader>
            <CardTitle>Webhook setup</CardTitle>
            <CardDescription>
              Finish this connection by adding a webhook in your own Meta App's dashboard (Webhooks
              product) with these exact values, so inbound messages and status updates reach you.
              The verify token is the same for every business connecting here - it's not a secret
              tied to your account, just a value Meta's one-time setup check expects.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <CopyableField label="Callback URL" value={connectorType.webhook_callback_url!} />
            <CopyableField label="Verify token" value={connectorType.webhook_verify_token!} />
          </CardContent>
        </Card>
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
                disabled={testMutation.isPending || !canManage}
                title={manageHint}
              >
                <RefreshCw className="h-3.5 w-3.5" />
                {testMutation.isPending ? "Testing…" : "Test connection"}
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={!canManage}
                title={manageHint}
                onClick={() => setConfirmingDisconnect(true)}
              >
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
