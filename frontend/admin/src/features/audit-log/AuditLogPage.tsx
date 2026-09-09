import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button, Card, CardContent, CardHeader, CardTitle, Input, Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@fusion-flow/ui";
import type { AuditLogFilters } from "../../lib/admin-types";
import { fetchAuditLog } from "../../lib/endpoints";

const PAGE_SIZE = 25;

export function AuditLogPage() {
  const [filters, setFilters] = useState<AuditLogFilters>({ limit: PAGE_SIZE, offset: 0 });
  const [draft, setDraft] = useState({ actor_user_id: "", tenant_id: "", action: "" });

  const { data, isLoading, isError } = useQuery({
    queryKey: ["admin", "audit-log", filters],
    queryFn: () => fetchAuditLog(filters),
  });

  function applyFilters() {
    setFilters({
      limit: PAGE_SIZE,
      offset: 0,
      actor_user_id: draft.actor_user_id || undefined,
      tenant_id: draft.tenant_id || undefined,
      action: draft.action || undefined,
    });
  }

  function resetFilters() {
    setDraft({ actor_user_id: "", tenant_id: "", action: "" });
    setFilters({ limit: PAGE_SIZE, offset: 0 });
  }

  const total = data?.total ?? 0;
  const offset = filters.offset ?? 0;
  const canPrev = offset > 0;
  const canNext = offset + PAGE_SIZE < total;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Audit log</h1>
        <p className="text-sm text-muted-foreground">
          One row per completed `/api/admin/*` request, written generically by the admin router's
          audit-logging middleware - not per-endpoint.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
            <Input
              placeholder="Actor user ID"
              value={draft.actor_user_id}
              onChange={(e) => setDraft((d) => ({ ...d, actor_user_id: e.target.value }))}
            />
            <Input
              placeholder="Tenant ID"
              value={draft.tenant_id}
              onChange={(e) => setDraft((d) => ({ ...d, tenant_id: e.target.value }))}
            />
            <Input
              placeholder="Action contains…"
              value={draft.action}
              onChange={(e) => setDraft((d) => ({ ...d, action: e.target.value }))}
            />
            <div className="flex gap-2">
              <Button className="flex-1" onClick={applyFilters}>
                Apply
              </Button>
              <Button variant="outline" onClick={resetFilters}>
                Reset
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4">
          <CardTitle>Events</CardTitle>
          <p className="text-xs text-muted-foreground">{total} total</p>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>}
          {isError && (
            <p className="py-8 text-center text-sm text-destructive">Could not load the audit log.</p>
          )}
          {!isLoading && !isError && (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>When</TableHead>
                    <TableHead>Actor</TableHead>
                    <TableHead>Action</TableHead>
                    <TableHead>Target</TableHead>
                    <TableHead>Tenant</TableHead>
                    <TableHead>IP</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(data?.items ?? []).map((entry) => (
                    <TableRow key={entry.id}>
                      <TableCell className="text-muted-foreground">
                        {new Date(entry.created_at).toLocaleString()}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {entry.actor_user_id ?? "unknown"}
                        {entry.actor_is_platform_admin && (
                          <span className="ml-1 text-muted-foreground">(admin)</span>
                        )}
                      </TableCell>
                      <TableCell className="font-medium text-foreground">{entry.action}</TableCell>
                      <TableCell className="text-muted-foreground">
                        {entry.target_type ? `${entry.target_type}/${entry.target_id ?? "?"}` : "—"}
                      </TableCell>
                      <TableCell className="font-mono text-xs text-muted-foreground">
                        {entry.tenant_id ?? "—"}
                      </TableCell>
                      <TableCell className="text-muted-foreground">{entry.ip_address ?? "—"}</TableCell>
                    </TableRow>
                  ))}
                  {(data?.items ?? []).length === 0 && (
                    <TableRow>
                      <TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">
                        No matching audit events.
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
              <div className="mt-4 flex items-center justify-between">
                <p className="text-xs text-muted-foreground">
                  Showing {Math.min(offset + 1, total)}-{Math.min(offset + PAGE_SIZE, total)} of {total}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!canPrev}
                    onClick={() => setFilters((f) => ({ ...f, offset: Math.max(0, offset - PAGE_SIZE) }))}
                  >
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!canNext}
                    onClick={() => setFilters((f) => ({ ...f, offset: offset + PAGE_SIZE }))}
                  >
                    Next
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
