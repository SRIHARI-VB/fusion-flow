import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MoreHorizontal, Search } from "lucide-react";
import {
  Badge,
  type BadgeVariant,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";
import type { BusinessStatus } from "@fusion-flow/ts-types";
import { approveTenant, denyTenant, fetchTenants, reactivateTenant, suspendTenant } from "../../lib/endpoints";

const statusVariant: Record<BusinessStatus, BadgeVariant> = {
  pending_approval: "secondary",
  active: "success",
  suspended: "destructive",
  denied: "outline",
};

const STATUS_FILTERS: { value: BusinessStatus | "all"; label: string }[] = [
  { value: "all", label: "All statuses" },
  { value: "pending_approval", label: "Pending approval" },
  { value: "active", label: "Active" },
  { value: "suspended", label: "Suspended" },
  { value: "denied", label: "Denied" },
];

export function TenantsPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<BusinessStatus | "all">("all");
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data: tenants, isLoading, isError } = useQuery({
    queryKey: ["admin", "tenants"],
    queryFn: fetchTenants,
  });

  const suspendMutation = useMutation({
    mutationFn: suspendTenant,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] }),
  });
  const reactivateMutation = useMutation({
    mutationFn: reactivateTenant,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] }),
  });
  const approveMutation = useMutation({
    mutationFn: approveTenant,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] }),
  });
  const denyMutation = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) => denyTenant(id, reason),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "tenants"] }),
  });

  const filtered = (tenants ?? []).filter((t) => {
    if (statusFilter !== "all" && t.status !== statusFilter) return false;
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return t.name.toLowerCase().includes(q) || t.slug.toLowerCase().includes(q);
  });

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Tenants</h1>
        <p className="text-sm text-muted-foreground">
          Every business on the platform. Suspend blocks their users' next login/refresh; reactivate
          restores access.
        </p>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between gap-4">
          <CardTitle>All tenants</CardTitle>
          <div className="flex items-center gap-2">
            <select
              className="h-9 rounded-md border border-input bg-card px-2 text-sm text-foreground"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as BusinessStatus | "all")}
            >
              {STATUS_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
            <div className="relative hidden sm:block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search tenants"
                className="h-9 w-56 pl-8 text-sm"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Loading tenants…</p>}
          {isError && (
            <p className="py-8 text-center text-sm text-destructive">
              Could not load tenants. Is the backend running and is your account platform-admin?
            </p>
          )}
          {!isLoading && !isError && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Business</TableHead>
                  <TableHead>Slug</TableHead>
                  <TableHead>Vertical</TableHead>
                  <TableHead>Members</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((tenant) => (
                  <TableRow key={tenant.id}>
                    <TableCell className="font-medium text-foreground">
                      <Link to={`/tenants/${tenant.id}`} className="hover:underline">
                        {tenant.name}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{tenant.slug}</TableCell>
                    <TableCell>{tenant.vertical ?? "—"}</TableCell>
                    <TableCell>{tenant.member_count}</TableCell>
                    <TableCell>
                      <Badge variant={statusVariant[tenant.status]}>{tenant.status}</Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {new Date(tenant.created_at).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger>
                          <Button variant="ghost" size="icon" aria-label={`Actions for ${tenant.name}`}>
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => navigate(`/tenants/${tenant.id}`)}>
                            View details
                          </DropdownMenuItem>
                          {tenant.status === "pending_approval" && (
                            <>
                              <DropdownMenuItem
                                onClick={() => approveMutation.mutate(tenant.id)}
                                disabled={approveMutation.isPending}
                              >
                                Approve
                              </DropdownMenuItem>
                              <DropdownMenuItem
                                onClick={() => {
                                  const reason = window.prompt("Reason for denial (optional)") ?? undefined;
                                  denyMutation.mutate({ id: tenant.id, reason });
                                }}
                                disabled={denyMutation.isPending}
                              >
                                Deny
                              </DropdownMenuItem>
                            </>
                          )}
                          {tenant.status === "active" && (
                            <DropdownMenuItem
                              onClick={() => suspendMutation.mutate(tenant.id)}
                              disabled={suspendMutation.isPending}
                            >
                              Suspend
                            </DropdownMenuItem>
                          )}
                          {tenant.status === "suspended" && (
                            <DropdownMenuItem
                              onClick={() => reactivateMutation.mutate(tenant.id)}
                              disabled={reactivateMutation.isPending}
                            >
                              Reactivate
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
                {filtered.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={7} className="py-8 text-center text-sm text-muted-foreground">
                      No tenants match "{search}".
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
