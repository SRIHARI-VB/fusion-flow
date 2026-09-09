import { Badge, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@fusion-flow/ui";
import type { BadgeVariant } from "@fusion-flow/ui";
import type { ConnectorEvent, ConnectorEventType } from "../types";

const EVENT_TYPE_DISPLAY: Record<ConnectorEventType, { label: string; variant: BadgeVariant }> = {
  webhook_received: { label: "Webhook", variant: "default" },
  sync: { label: "Sync", variant: "secondary" },
  oauth_callback: { label: "OAuth callback", variant: "outline" },
  error: { label: "Error", variant: "destructive" },
};

interface ConnectorEventsTableProps {
  events: ConnectorEvent[];
  isLoading?: boolean;
}

export function ConnectorEventsTable({ events, isLoading }: ConnectorEventsTableProps) {
  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading event history…</p>;
  }
  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">No events recorded yet for this connector.</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Type</TableHead>
          <TableHead>Occurred</TableHead>
          <TableHead>Payload</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {events.map((event) => {
          const display = EVENT_TYPE_DISPLAY[event.event_type];
          return (
            <TableRow key={event.id}>
              <TableCell>
                <Badge variant={display.variant}>{display.label}</Badge>
              </TableCell>
              <TableCell className="whitespace-nowrap text-sm text-muted-foreground">
                {new Date(event.occurred_at).toLocaleString()}
              </TableCell>
              <TableCell>
                <pre className="max-w-lg overflow-x-auto whitespace-pre-wrap text-xs text-muted-foreground">
                  {JSON.stringify(event.payload, null, 2)}
                </pre>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
