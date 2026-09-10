import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@fusion-flow/ui";
import type { BadgeVariant } from "@fusion-flow/ui";
import {
  approveConnectorAccessRequest,
  denyConnectorAccessRequest,
  fetchConnectorAccessRequests,
} from "../../lib/endpoints";
import type { ConnectorAccessRequestStatus } from "../../lib/admin-types";

const statusVariant: Record<ConnectorAccessRequestStatus, BadgeVariant> = {
  pending: "secondary",
  approved: "success",
  denied: "destructive",
};

/**
 * `/connector-requests` — cross-tenant queue of `ConnectorAccessRequest`
 * rows (pending-first, per `GET /api/admin/connector-access-requests`).
 * A tenant lands here by requesting a connector outside its
 * business-template bundle from `/connectors` in the tenant app.
 */
export function ConnectorRequestsPage() {
  const queryClient = useQueryClient();

  const { data: requests, isLoading, isError } = useQuery({
    queryKey: ["admin", "connector-access-requests"],
    queryFn: () => fetchConnectorAccessRequests(),
  });

  function invalidate() {
    void queryClient.invalidateQueries({ queryKey: ["admin", "connector-access-requests"] });
  }

  const approveMutation = useMutation({
    mutationFn: (requestId: string) => approveConnectorAccessRequest(requestId),
    onSuccess: invalidate,
  });
  const denyMutation = useMutation({
    mutationFn: (requestId: string) => denyConnectorAccessRequest(requestId),
    onSuccess: invalidate,
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Connector access requests</h1>
        <p className="text-sm text-muted-foreground">
          A tenant asking for a connector outside its business-template bundle. Approving grants it
          immediately; the tenant can request again later if denied.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Requests</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>}
          {isError && (
            <p className="py-8 text-center text-sm text-destructive">Could not load connector access requests.</p>
          )}
          {!isLoading && !isError && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Tenant</TableHead>
                  <TableHead>Connector</TableHead>
                  <TableHead>Requested by</TableHead>
                  <TableHead>Reason</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-40" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(requests ?? []).map((req) => (
                  <TableRow key={req.id}>
                    <TableCell className="font-medium text-foreground">{req.business_name}</TableCell>
                    <TableCell className="font-mono text-sm">{req.connector_type_key}</TableCell>
                    <TableCell className="text-muted-foreground">{req.requested_by_email ?? req.requested_by}</TableCell>
                    <TableCell className="max-w-xs truncate text-muted-foreground">{req.reason ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariant[req.status]}>{req.status}</Badge>
                    </TableCell>
                    <TableCell className="flex flex-wrap gap-2">
                      {req.status === "pending" && (
                        <>
                          <Button
                            size="sm"
                            variant="success"
                            onClick={() => approveMutation.mutate(req.id)}
                            disabled={approveMutation.isPending || denyMutation.isPending}
                          >
                            Approve
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => denyMutation.mutate(req.id)}
                            disabled={approveMutation.isPending || denyMutation.isPending}
                          >
                            Deny
                          </Button>
                        </>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
                {(requests ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                      No connector access requests yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
