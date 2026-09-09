import { useNavigate } from "react-router-dom";
import { Activity, RefreshCw, Unplug, Webhook } from "lucide-react";
import { Badge, Button, Card, CardContent, CardFooter, CardHeader, CardTitle } from "@fusion-flow/ui";
import type { ConnectorInstance, ConnectorType } from "../types";
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
 */
interface ConnectorCardProps {
  connectorType: ConnectorType;
  instance?: ConnectorInstance;
  onTest?: (instanceId: string) => void;
  onDisconnect?: (instanceId: string) => void;
  testBusy?: boolean;
}

export function ConnectorCard({ connectorType, instance, onTest, onDisconnect, testBusy }: ConnectorCardProps) {
  const navigate = useNavigate();
  const Icon = CONNECTOR_CATEGORY_ICON[connectorType.category];
  const state = instance?.state;
  const stateDisplay = CONNECTOR_STATE_DISPLAY[state ?? "not_connected"];
  const healthDisplay = instance?.health_status ? CONNECTOR_HEALTH_DISPLAY[instance.health_status] : null;
  const canConnect = isReconnectable(state);

  return (
    <Card className="flex flex-col">
      <CardHeader className="flex-row items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-accent">
            <Icon className="h-5 w-5" />
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
        {instance?.last_error_message && (
          <p className="text-xs text-destructive">{instance.last_error_message}</p>
        )}
      </CardContent>

      <CardFooter className="justify-end gap-2">
        {instance && !canConnect && (
          <>
            <Button
              variant="outline"
              size="sm"
              onClick={() => onTest?.(instance.id)}
              disabled={testBusy}
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Test
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => onDisconnect?.(instance.id)}
            >
              <Unplug className="h-3.5 w-3.5" />
              Disconnect
            </Button>
          </>
        )}
        {canConnect && (
          <Button size="sm" onClick={() => navigate(`/connectors/${connectorType.key}/connect`)}>
            {state ? "Reconnect" : "Connect"}
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
