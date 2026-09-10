import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { ArrowLeft, Blocks, CreditCard, Gauge, Plug, ShieldQuestion, Users } from "lucide-react";
import {
  Badge,
  type BadgeVariant,
  Button,
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  Input,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";
import type { BusinessStatus } from "@fusion-flow/ts-types";
import { Modal } from "../../components/Modal";
import {
  approveTenant,
  assignTenantPlan,
  clearConnectorAccessOverride,
  clearTenantResourceLimit,
  denyTenant,
  fetchPlans,
  fetchTenantConnectors,
  fetchTenantDetail,
  fetchTenantModuleAccess,
  fetchTenantResourceLimits,
  impersonateTenantUser,
  reactivateTenant,
  setConnectorAccessOverride,
  setTenantResourceLimit,
  suspendTenant,
} from "../../lib/endpoints";

const statusVariant: Record<BusinessStatus, BadgeVariant> = {
  pending_approval: "secondary",
  active: "success",
  suspended: "destructive",
  denied: "outline",
};

const accessStatusVariant: Record<string, BadgeVariant> = {
  granted: "success",
  pending: "secondary",
  denied: "destructive",
  not_requested: "outline",
};

export function TenantDetailPage() {
  const { id } = useParams<{ id: string }>();
  const tenantId = id ?? "";
  const queryClient = useQueryClient();

  const [impersonateOpen, setImpersonateOpen] = useState(false);
  const [impersonateUserId, setImpersonateUserId] = useState("");
  const [impersonateReason, setImpersonateReason] = useState("");
  const [impersonateResult, setImpersonateResult] = useState<string | null>(null);
  const [impersonateError, setImpersonateError] = useState<string | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string>("");

  const { data: tenant, isLoading, isError } = useQuery({
    queryKey: ["admin", "tenants", tenantId],
    queryFn: () => fetchTenantDetail(tenantId),
    enabled: !!tenantId,
  });

  const { data: connectors } = useQuery({
    queryKey: ["admin", "tenants", tenantId, "connectors"],
    queryFn: () => fetchTenantConnectors(tenantId),
    enabled: !!tenantId,
  });

  const { data: moduleAccess } = useQuery({
    queryKey: ["admin", "tenants", tenantId, "module-access"],
    queryFn: () => fetchTenantModuleAccess(tenantId),
    enabled: !!tenantId,
  });

  const { data: resourceLimits } = useQuery({
    queryKey: ["admin", "tenants", tenantId, "resource-limits"],
    queryFn: () => fetchTenantResourceLimits(tenantId),
    enabled: !!tenantId,
  });
  const [limitInputs, setLimitInputs] = useState<Record<string, string>>({});

  const { data: plans } = useQuery({ queryKey: ["admin", "plans"], queryFn: fetchPlans });

  const assignPlanMutation = useMutation({
    mutationFn: () => assignTenantPlan(tenantId, selectedPlanId || null),
  });

  const suspendMutation = useMutation({
    mutationFn: () => suspendTenant(tenantId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "tenants", tenantId] }),
  });
  const reactivateMutation = useMutation({
    mutationFn: () => reactivateTenant(tenantId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "tenants", tenantId] }),
  });
  const approveMutation = useMutation({
    mutationFn: () => approveTenant(tenantId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "tenants", tenantId] }),
  });
  const denyMutation = useMutation({
    mutationFn: (reason?: string) => denyTenant(tenantId, reason),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "tenants", tenantId] }),
  });

  function invalidateModuleAccess() {
    void queryClient.invalidateQueries({ queryKey: ["admin", "tenants", tenantId, "module-access"] });
  }
  const revokeMutation = useMutation({
    mutationFn: (typeKey: string) =>
      setConnectorAccessOverride(tenantId, typeKey, { granted: false, reason: "Revoked by admin" }),
    onSuccess: invalidateModuleAccess,
  });
  const grantMutation = useMutation({
    mutationFn: (typeKey: string) =>
      setConnectorAccessOverride(tenantId, typeKey, { granted: true, reason: "Granted by admin" }),
    onSuccess: invalidateModuleAccess,
  });
  const resetOverrideMutation = useMutation({
    mutationFn: (typeKey: string) => clearConnectorAccessOverride(tenantId, typeKey),
    onSuccess: invalidateModuleAccess,
  });
  const moduleActionBusy = revokeMutation.isPending || grantMutation.isPending || resetOverrideMutation.isPending;

  function invalidateResourceLimits() {
    void queryClient.invalidateQueries({ queryKey: ["admin", "tenants", tenantId, "resource-limits"] });
  }
  const saveLimitMutation = useMutation({
    mutationFn: ({ resourceKey, maxCount }: { resourceKey: string; maxCount: number }) =>
      setTenantResourceLimit(tenantId, resourceKey, maxCount),
    onSuccess: (_result, { resourceKey }) => {
      invalidateResourceLimits();
      setLimitInputs((inputs) => {
        const next = { ...inputs };
        delete next[resourceKey];
        return next;
      });
    },
  });
  const clearLimitMutation = useMutation({
    mutationFn: (resourceKey: string) => clearTenantResourceLimit(tenantId, resourceKey),
    onSuccess: invalidateResourceLimits,
  });

  const impersonateMutation = useMutation({
    mutationFn: () =>
      impersonateTenantUser(tenantId, { target_user_id: impersonateUserId, reason: impersonateReason }),
    onSuccess: (result) => {
      setImpersonateError(null);
      setImpersonateResult(result.access_token);
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setImpersonateResult(null);
      setImpersonateError(axiosErr.response?.data?.detail ?? "Failed to start impersonation session.");
    },
  });

  function closeImpersonateModal() {
    setImpersonateOpen(false);
    setImpersonateUserId("");
    setImpersonateReason("");
    setImpersonateResult(null);
    setImpersonateError(null);
  }

  if (isLoading) {
    return <p className="py-8 text-center text-sm text-muted-foreground">Loading tenant…</p>;
  }
  if (isError || !tenant) {
    return <p className="py-8 text-center text-sm text-destructive">Could not load this tenant.</p>;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <Link
            to="/tenants"
            className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            Back to tenants
          </Link>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-semibold text-foreground">{tenant.name}</h1>
            <Badge variant={statusVariant[tenant.status]}>{tenant.status}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {tenant.slug} · {tenant.vertical ?? "no vertical set"}
          </p>
          {tenant.status === "denied" && tenant.denial_reason && (
            <p className="mt-1 text-sm text-destructive">Denial reason: {tenant.denial_reason}</p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {tenant.status === "pending_approval" && (
            <>
              <Button variant="success" onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending}>
                Approve
              </Button>
              <Button
                variant="destructive"
                onClick={() => {
                  const reason = window.prompt("Reason for denial (optional)") ?? undefined;
                  denyMutation.mutate(reason);
                }}
                disabled={denyMutation.isPending}
              >
                Deny
              </Button>
            </>
          )}
          {tenant.status === "active" && (
            <Button variant="destructive" onClick={() => suspendMutation.mutate()} disabled={suspendMutation.isPending}>
              Suspend tenant
            </Button>
          )}
          {tenant.status === "suspended" && (
            <Button variant="success" onClick={() => reactivateMutation.mutate()} disabled={reactivateMutation.isPending}>
              Reactivate tenant
            </Button>
          )}
          <Button variant="outline" onClick={() => setImpersonateOpen(true)}>
            <ShieldQuestion className="h-4 w-4" />
            Impersonate
          </Button>
        </div>
      </div>

      <Card>
        <CardHeader className="flex-row items-center gap-2">
          <Users className="h-4 w-4 text-muted-foreground" />
          <CardTitle>Memberships</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Invited</TableHead>
                <TableHead>Accepted</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {tenant.memberships.map((m) => (
                <TableRow key={m.user_id}>
                  <TableCell className="font-medium text-foreground">{m.email}</TableCell>
                  <TableCell className="capitalize">{m.role}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {new Date(m.invited_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {m.accepted_at ? new Date(m.accepted_at).toLocaleDateString() : "Pending"}
                  </TableCell>
                </TableRow>
              ))}
              {tenant.memberships.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="py-6 text-center text-sm text-muted-foreground">
                    No members.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center gap-2">
          <CreditCard className="h-4 w-4 text-muted-foreground" />
          <CardTitle>Plan</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          {/* TenantDetailOut doesn't expose the tenant's *current* plan_id
              yet (Business.plan_id doesn't exist on the ORM model in this
              checkout - see this task's report), so this is assign-only for
              now; showing the current selection needs that column plus a
              small TenantDetailOut addition once it lands. */}
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-medium text-muted-foreground" htmlFor="tenant-plan">
              Assign plan
            </label>
            <select
              id="tenant-plan"
              className="h-10 w-56 rounded-md border border-input bg-card px-3 text-sm text-foreground"
              value={selectedPlanId}
              onChange={(e) => setSelectedPlanId(e.target.value)}
            >
              <option value="">No plan</option>
              {(plans ?? []).map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </div>
          <Button onClick={() => assignPlanMutation.mutate()} disabled={assignPlanMutation.isPending}>
            Assign
          </Button>
          {assignPlanMutation.isSuccess && (
            <span className="text-sm text-success">Plan assigned.</span>
          )}
        </CardContent>
      </Card>

      {/* Connector health section hides gracefully rather than erroring if
          modules.connectors hasn't landed in this checkout yet - see
          fetchTenantConnectors / ConnectorHealth.available. */}
      {connectors?.available && (
        <Card>
          <CardHeader className="flex-row items-center gap-2">
            <Plug className="h-4 w-4 text-muted-foreground" />
            <CardTitle>Connector health</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Connector</TableHead>
                  <TableHead>State</TableHead>
                  <TableHead>Last webhook</TableHead>
                  <TableHead>Last sync</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {connectors.connectors.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="font-medium text-foreground">{c.connector_type_key}</TableCell>
                    <TableCell className="capitalize">{c.state.replace(/_/g, " ")}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {c.last_webhook_at ? new Date(c.last_webhook_at).toLocaleString() : "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {c.last_sync_at ? new Date(c.last_sync_at).toLocaleString() : "—"}
                    </TableCell>
                  </TableRow>
                ))}
                {connectors.connectors.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="py-6 text-center text-sm text-muted-foreground">
                      No connectors set up yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="flex-row items-center gap-2">
          <Blocks className="h-4 w-4 text-muted-foreground" />
          <CardTitle>Modules &amp; connectors</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-3 text-xs text-muted-foreground">
            Revoke or grant a single module/connector for this tenant, independent of its business
            template or any request - an override always wins until reset.
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Item</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Access</TableHead>
                <TableHead className="w-64" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(moduleAccess ?? []).map((item) => (
                <TableRow key={item.connector_type_id}>
                  <TableCell className="font-medium text-foreground">
                    {item.display_name}
                    <span className="ml-1 font-mono text-xs text-muted-foreground">({item.connector_type_key})</span>
                  </TableCell>
                  <TableCell className="capitalize text-muted-foreground">
                    {item.category === "feature" ? "Module" : "Integration"}
                  </TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <Badge variant={accessStatusVariant[item.access_status] ?? "outline"}>
                        {item.access_status.replace(/_/g, " ")}
                      </Badge>
                      {item.has_override && (
                        <Badge variant="outline" className="text-[10px]">
                          override: {item.override_granted ? "granted" : "revoked"}
                        </Badge>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="flex flex-wrap gap-2">
                    {item.access_status === "granted" ? (
                      <Button
                        size="sm"
                        variant="destructive"
                        disabled={moduleActionBusy}
                        onClick={() => revokeMutation.mutate(item.connector_type_key)}
                      >
                        Revoke
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="success"
                        disabled={moduleActionBusy}
                        onClick={() => grantMutation.mutate(item.connector_type_key)}
                      >
                        Grant
                      </Button>
                    )}
                    {item.has_override && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={moduleActionBusy}
                        onClick={() => resetOverrideMutation.mutate(item.connector_type_key)}
                      >
                        Reset to default
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {(moduleAccess ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="py-6 text-center text-sm text-muted-foreground">
                    No catalog items found.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center gap-2">
          <Gauge className="h-4 w-4 text-muted-foreground" />
          <CardTitle>Resource limits</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="mb-3 text-xs text-muted-foreground">
            Set an explicit ceiling for this tenant, independent of its plan - always wins until reset.
            Leave the plan's own default alone from the Plans page.
          </p>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Resource</TableHead>
                <TableHead>Effective limit</TableHead>
                <TableHead>Source</TableHead>
                <TableHead className="w-72" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {(resourceLimits ?? []).map((item) => (
                <TableRow key={item.connector_type_id}>
                  <TableCell className="font-medium text-foreground">
                    {item.display_name}
                    <span className="ml-1 font-mono text-xs text-muted-foreground">({item.resource_key})</span>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {item.limit === null ? "unlimited" : `up to ${item.limit}`}
                  </TableCell>
                  <TableCell>
                    <Badge variant={item.source === "tenant_override" ? "secondary" : "outline"}>
                      {item.source === "tenant_override"
                        ? "tenant override"
                        : item.source === "plan"
                          ? "plan default"
                          : "unlimited"}
                    </Badge>
                  </TableCell>
                  <TableCell className="flex flex-wrap items-center gap-2">
                    <Input
                      type="number"
                      min={0}
                      placeholder="set limit"
                      className="h-9 w-24"
                      value={limitInputs[item.resource_key] ?? ""}
                      onChange={(e) =>
                        setLimitInputs((inputs) => ({ ...inputs, [item.resource_key]: e.target.value }))
                      }
                    />
                    <Button
                      size="sm"
                      disabled={!limitInputs[item.resource_key] || saveLimitMutation.isPending}
                      onClick={() =>
                        saveLimitMutation.mutate({
                          resourceKey: item.resource_key,
                          maxCount: Number(limitInputs[item.resource_key]),
                        })
                      }
                    >
                      Set
                    </Button>
                    {item.source === "tenant_override" && (
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={clearLimitMutation.isPending}
                        onClick={() => clearLimitMutation.mutate(item.resource_key)}
                      >
                        Reset
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
              {(resourceLimits ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="py-6 text-center text-sm text-muted-foreground">
                    No limitable resources found.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Modal
        open={impersonateOpen}
        onClose={closeImpersonateModal}
        title="Impersonate a user"
        description="Requires a reason - recorded permanently in this tenant's impersonation history and the audit log."
      >
        {impersonateResult ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm text-foreground">
              Impersonation token minted. Copy it to act as this user (expires shortly):
            </p>
            <textarea
              readOnly
              className="h-24 w-full resize-none rounded-md border border-input bg-muted p-2 text-xs text-foreground"
              value={impersonateResult}
            />
            <Button variant="outline" onClick={closeImpersonateModal}>
              Close
            </Button>
          </div>
        ) : (
          <form
            className="flex flex-col gap-4"
            onSubmit={(e) => {
              e.preventDefault();
              impersonateMutation.mutate();
            }}
          >
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium" htmlFor="impersonate-user-id">
                Target user ID
              </label>
              <Input
                id="impersonate-user-id"
                placeholder="user UUID (from the memberships table above)"
                value={impersonateUserId}
                onChange={(e) => setImpersonateUserId(e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium" htmlFor="impersonate-reason">
                Reason
              </label>
              <Input
                id="impersonate-reason"
                placeholder="e.g. investigating support ticket #1234"
                value={impersonateReason}
                onChange={(e) => setImpersonateReason(e.target.value)}
                required
              />
            </div>
            {impersonateError && <p className="text-sm text-destructive">{impersonateError}</p>}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="ghost" onClick={closeImpersonateModal}>
                Cancel
              </Button>
              <Button type="submit" disabled={impersonateMutation.isPending}>
                Start impersonation
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
}
