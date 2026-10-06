import { useNavigate } from "react-router-dom";
import { Activity, Clock, Lock, RefreshCw, Unplug, Webhook } from "lucide-react";
import { Badge, Button, Card, CardContent, CardFooter, CardHeader, CardTitle } from "@fusion-flow/ui";
import { useCanManageAccess } from "../../../lib/useModuleAccess";
import type { ConnectorInstance, ConnectorType } from "../types";
import { CONNECTOR_LOGO, CONNECTOR_LOGO_COLOR } from "../connector-logos";
import {
  CONNECTOR_CATEGORY_ICON,
  CONNECTOR_HEALTH_DISPLAY,
  CONNECTOR_STATE_DISPLAY,
  formatRelativeTimestamp,
  isReconnectable,
} from "../state-display";

/**
 * Generic connector card - renders any `connector_types` row + the
 * tenant's matching `connector_instances` row (if connected yet) off the
 * same two backend endpoints regardless of provider. Never renders
 * anything from `connected_identity`/`provider_ref_ids` beyond what the
 * backend already returns - both are adapter-populated safe allowlists,
 * never raw credentials (`connector_credentials` is never even sent to
 * the client - see `types.ts`'s module docstring).
 *
 * `connectorType.access_status` gates Connect/Reconnect entirely: outside
 * the tenant's business-template bundle (and with no approved access
 * request), the backend's `connect()` 403s anyway - this card shows
 * "Request access" / "Pending admin approval" instead of a CTA that would
 * just fail.
 */
interface ConnectorCardProps {
  connectorType: ConnectorType;
  instance?: ConnectorInstance;
  onTest?: (instanceId: string) => void;
  onDisconnect?: (instanceId: string) => void;
  onRequestAccess?: (typeKey: string) => void;
  testBusy?: boolean;
  requestAccessBusy?: boolean;
}

export function ConnectorCard({
  connectorType,
  instance,
  onTest,
  onDisconnect,
  onRequestAccess,
  testBusy,
  requestAccessBusy,
}: ConnectorCardProps) {
  const navigate = useNavigate();
  // Connect/Disconnect/Test/Request-access are Owner/Admin only at the API (403).
  const { canManage } = useCanManageAccess();
  const manageHint = canManage ? undefined : "Only an Owner or Admin can manage connectors.";
  // Real per-provider brand mark when one exists, falling back to a
  // generic category icon shared by every connector in that category
  // (e.g. a future connector added before its logo lands) - see
  // `connector-logos.tsx`'s module docstring.
  const Icon = CONNECTOR_LOGO[connectorType.key] ?? CONNECTOR_CATEGORY_ICON[connectorType.category];
  // Only the real brand marks get their own brand color - the generic
  // category fallback keeps inheriting `text-accent` via `currentColor`.
  const logoColor = CONNECTOR_LOGO_COLOR[connectorType.key];
  const state = instance?.state;
  const stateDisplay = CONNECTOR_STATE_DISPLAY[state ?? "not_connected"];
  const healthDisplay = instance?.health_status ? CONNECTOR_HEALTH_DISPLAY[instance.health_status] : null;
  const isGranted = connectorType.access_status === "granted";
  const canConnect = isReconnectable(state) && isGranted;

  return (
    <Card className="flex flex-col">
      <CardHeader className="flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-accent">
            <Icon className="h-5 w-5" color={logoColor} />
          </div>
          <div>
            <CardTitle>{instance?.display_name ?? connectorType.display_name}</CardTitle>
            <p className="text-xs capitalize text-muted-foreground">{connectorType.category.replace("_", " ")}</p>
          </div>
        </div>
        <Badge variant={stateDisplay.variant}>{stateDisplay.label}</Badge>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-2 text-sm text-muted-foreground">
        {healthDisplay && (
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            <span>Health:</span>
            <Badge variant={healthDisplay.variant}>{healthDisplay.label}</Badge>
          </div>
        )}
        <div className="flex items-center gap-2">
          <Webhook className="h-4 w-4" />
          <span>Last webhook: {formatRelativeTimestamp(instance?.last_webhook_at)}</span>
        </div>
        {!canManage && (
          <p className="text-xs">Read-only for your role - ask an Owner or Admin to connect or change this.</p>
        )}
        {instance?.last_error_message && (
          <p className="text-xs text-destructive">{instance.last_error_message}</p>
        )}
      </CardContent>

      <CardFooter className="justify-end gap-2">
        {instance && !isReconnectable(state) && (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onTest?.(instance.id)}
              disabled={testBusy || !canManage}
              title={manageHint}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Test
            </Button>
            <Button
              variant="destructive"
              size="sm"
              disabled={!canManage}
              title={manageHint}
              onClick={() => onDisconnect?.(instance.id)}
            >
              <Unplug className="h-3.5 w-3.5" />
              Disconnect
            </Button>
          </>
        )}
        {canConnect && (
          <Button
            size="sm"
            disabled={!canManage}
            title={manageHint}
            onClick={() => navigate(`/connectors/${connectorType.key}/connect`)}
          >
            {state ? "Reconnect" : "Connect"}
          </Button>
        )}
        {isReconnectable(state) && !isGranted && connectorType.access_status === "pending" && (
          <Badge variant="secondary">
            <Clock className="h-3.5 w-3.5" />
            Pending admin approval
          </Badge>
        )}
        {isReconnectable(state) && !isGranted && connectorType.access_status !== "pending" && (
          <Button
            size="sm"
            variant="outline"
            onClick={() => onRequestAccess?.(connectorType.key)}
            disabled={requestAccessBusy || !canManage}
            title={manageHint}
          >
            <Lock className="h-3.5 w-3.5" />
            {connectorType.access_status === "denied" ? "Request access again" : "Request access"}
          </Button>
        )}
        {instance && (
          <Button variant="ghost" size="sm" onClick={() => navigate(`/connectors/${instance.id}`)}>
            Details
          </Button>
        )}
      </CardFooter>
    </Card>
  );
}
