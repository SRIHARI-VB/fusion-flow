import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";
import type { BadgeVariant } from "@fusion-flow/ui";
import {
  approveConnectorAccessRequest,
  denyConnectorAccessRequest,
  fetchConnectorAccessRequests,
} from "../../lib/endpoints";
import type { ConnectorAccessRequestAdmin, ConnectorAccessRequestStatus } from "../../lib/admin-types";
import { formatDaysAgo } from "../../lib/relative-time";

const statusVariant: Record<ConnectorAccessRequestStatus, BadgeVariant> = {
  pending: "secondary",
  approved: "success",
  denied: "destructive",
};

type GroupBy = "tenant" | "none";

interface TenantGroup {
  tenantId: string;
  businessName: string;
  isNewSignup: boolean;
  requests: ConnectorAccessRequestAdmin[];
  pendingIds: string[];
  oldestCreatedAt: string;
}

function DaysAgoTag({ createdAt }: { createdAt: string }) {
  return (
    <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
      {formatDaysAgo(createdAt)}
    </span>
  );
}

function OriginBadge({ isNewSignup }: { isNewSignup: boolean }) {
  return isNewSignup ? (
    <Badge variant="default" className="text-[10px]">
      New signup
    </Badge>
  ) : (
    <Badge variant="outline" className="text-[10px]">
      Additional request
    </Badge>
  );
}

/**
 * `/connector-requests` — cross-tenant queue of `ConnectorAccessRequest`
 * rows (pending-first, per `GET /api/admin/connector-access-requests`).
 * A tenant lands here either by requesting extra modules/connectors at
 * signup (business still `pending_approval` - see `OriginBadge`) or by
 * requesting a connector outside its bundle later, once already active.
 *
 * Defaults to grouping by tenant: a new signup can file several requests
 * at once (one per extra module/connector picked on the signup form), and
 * reviewing them one row at a time made it hard to tell they all belonged
 * to the same application - grouping surfaces that plus a bulk
 * approve/deny action per tenant.
 */
export function ConnectorRequestsPage() {
  const queryClient = useQueryClient();
  const [groupBy, setGroupBy] = useState<GroupBy>("tenant");
  const [collapsedTenants, setCollapsedTenants] = useState<Set<string>>(new Set());

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
  const bulkApproveMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      for (const id of ids) await approveConnectorAccessRequest(id);
    },
    onSuccess: invalidate,
  });
  const bulkDenyMutation = useMutation({
    mutationFn: async (ids: string[]) => {
      for (const id of ids) await denyConnectorAccessRequest(id);
    },
    onSuccess: invalidate,
  });

  const anyMutationBusy =
    approveMutation.isPending ||
    denyMutation.isPending ||
    bulkApproveMutation.isPending ||
    bulkDenyMutation.isPending;

  const groups = useMemo<TenantGroup[]>(() => {
    const order: string[] = [];
    const byTenant = new Map<string, ConnectorAccessRequestAdmin[]>();
    for (const req of requests ?? []) {
      if (!byTenant.has(req.tenant_id)) {
        byTenant.set(req.tenant_id, []);
        order.push(req.tenant_id);
      }
      byTenant.get(req.tenant_id)!.push(req);
    }
    return order.map((tenantId) => {
      const reqs = byTenant.get(tenantId)!;
      return {
        tenantId,
        businessName: reqs[0].business_name,
        isNewSignup: reqs[0].business_status === "pending_approval",
        requests: reqs,
        pendingIds: reqs.filter((r) => r.status === "pending").map((r) => r.id),
        oldestCreatedAt: reqs.reduce(
          (oldest, r) => (r.created_at < oldest ? r.created_at : oldest),
          reqs[0].created_at,
        ),
      };
    });
  }, [requests]);

  function toggleCollapsed(tenantId: string) {
    setCollapsedTenants((prev) => {
      const next = new Set(prev);
      if (next.has(tenantId)) next.delete(tenantId);
      else next.add(tenantId);
      return next;
    });
  }

  function renderRequestRow(req: ConnectorAccessRequestAdmin, opts: { showTenant: boolean }) {
    return (
      <TableRow key={req.id}>
        {opts.showTenant && (
          <TableCell className="font-medium text-foreground">
            <div className="flex items-center gap-2">
              {req.business_name}
              <OriginBadge isNewSignup={req.business_status === "pending_approval"} />
            </div>
          </TableCell>
        )}
        <TableCell className="font-mono text-sm">{req.connector_type_key}</TableCell>
        <TableCell className="text-muted-foreground">{req.requested_by_email ?? req.requested_by}</TableCell>
        <TableCell className="max-w-xs truncate text-muted-foreground">{req.reason ?? "—"}</TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <Badge variant={statusVariant[req.status]}>{req.status}</Badge>
            <DaysAgoTag createdAt={req.created_at} />
          </div>
        </TableCell>
        <TableCell className="flex flex-wrap gap-2">
          {req.status === "pending" && (
            <>
              <Button
                size="sm"
                variant="success"
                onClick={() => approveMutation.mutate(req.id)}
                disabled={anyMutationBusy}
              >
                Approve
              </Button>
              <Button
                size="sm"
                variant="destructive"
                onClick={() => denyMutation.mutate(req.id)}
                disabled={anyMutationBusy}
              >
                Deny
              </Button>
            </>
          )}
        </TableCell>
      </TableRow>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Connector access requests</h1>
        <p className="text-sm text-muted-foreground">
          A tenant asking for a module or connector outside its business-template bundle - either
          picked as an add-on at signup, or requested later once already active. Approving grants
          it immediately; the tenant can request again later if denied. Denying only declines the request - it does not revoke access already granted by a template or override (use the tenant's Modules & connectors panel for that).
        </p>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4">
          <CardTitle>Requests</CardTitle>
          <div className="flex items-center gap-2">
            <label htmlFor="group-by" className="text-sm text-muted-foreground">
              Group by
            </label>
            <select
              id="group-by"
              className="h-9 rounded-md border border-input bg-card px-2 text-sm text-foreground"
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value as GroupBy)}
            >
              <option value="tenant">Tenant</option>
              <option value="none">None</option>
            </select>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>}
          {isError && (
            <p className="py-8 text-center text-sm text-destructive">Could not load connector access requests.</p>
          )}
          {!isLoading && !isError && (requests ?? []).length === 0 && (
            <p className="py-8 text-center text-sm text-muted-foreground">No connector access requests yet.</p>
          )}

          {!isLoading && !isError && (requests ?? []).length > 0 && groupBy === "none" && (
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
              <TableBody>{(requests ?? []).map((req) => renderRequestRow(req, { showTenant: true }))}</TableBody>
            </Table>
          )}

          {!isLoading && !isError && groups.length > 0 && groupBy === "tenant" && (
            <div className="flex flex-col gap-3">
              {groups.map((group) => {
                const collapsed = collapsedTenants.has(group.tenantId);
                return (
                  <div key={group.tenantId} className="rounded-lg border border-border">
                    <div className="flex flex-wrap items-center justify-between gap-3 p-3">
                      <button
                        type="button"
                        onClick={() => toggleCollapsed(group.tenantId)}
                        className="flex items-center gap-2 text-left"
                      >
                        {collapsed ? (
                          <ChevronRight className="h-4 w-4 text-muted-foreground" />
                        ) : (
                          <ChevronDown className="h-4 w-4 text-muted-foreground" />
                        )}
                        <span className="text-sm font-semibold text-foreground">{group.businessName}</span>
                        <OriginBadge isNewSignup={group.isNewSignup} />
                        <span className="text-xs text-muted-foreground">
                          {group.requests.length} request{group.requests.length === 1 ? "" : "s"}
                          {group.pendingIds.length > 0 && ` · ${group.pendingIds.length} pending`}
                        </span>
                        <DaysAgoTag createdAt={group.oldestCreatedAt} />
                      </button>
                      {group.pendingIds.length > 0 && (
                        <div className="flex gap-2">
                          <Button
                            size="sm"
                            variant="success"
                            disabled={anyMutationBusy}
                            onClick={() => bulkApproveMutation.mutate(group.pendingIds)}
                          >
                            Approve all pending ({group.pendingIds.length})
                          </Button>
                          <Button
                            size="sm"
                            variant="destructive"
                            disabled={anyMutationBusy}
                            onClick={() => bulkDenyMutation.mutate(group.pendingIds)}
                          >
                            Deny all pending
                          </Button>
                        </div>
                      )}
                    </div>
                    {!collapsed && (
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Connector</TableHead>
                            <TableHead>Requested by</TableHead>
                            <TableHead>Reason</TableHead>
                            <TableHead>Status</TableHead>
                            <TableHead className="w-40" />
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {group.requests.map((req) => renderRequestRow(req, { showTenant: false }))}
                        </TableBody>
                      </Table>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
