import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { Plus } from "lucide-react";
import {
  Badge,
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
import { Modal } from "../../components/Modal";
import {
  createPlan,
  fetchFeatureFlags,
  fetchPlanFeatureFlags,
  fetchPlanResourceLimits,
  fetchPlans,
  setPlanFeatureFlags,
  setPlanResourceLimits,
  updatePlan,
} from "../../lib/endpoints";

/**
 * `/plans` — CRUD for `Plan` (billing/entitlement tiers) plus, per plan,
 * which feature flags it grants. `is_feature_enabled`'s resolution order
 * (backend `modules/admin/service.py`) reads this bundle for any tenant on
 * this plan, between a tenant-specific override and the flag's global
 * default/override.
 */
export function PlansPage() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ key: "", name: "", is_default: false });
  const [createError, setCreateError] = useState<string | null>(null);
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  const [pendingFlagEdits, setPendingFlagEdits] = useState<Record<string, boolean>>({});
  // Keyed by resource_key. "" input means "unlimited" (max_count=null on save).
  const [pendingLimitEdits, setPendingLimitEdits] = useState<Record<string, string>>({});

  const { data: plans, isLoading, isError } = useQuery({
    queryKey: ["admin", "plans"],
    queryFn: fetchPlans,
  });

  const { data: allFlags } = useQuery({ queryKey: ["admin", "feature-flags"], queryFn: fetchFeatureFlags });

  const { data: planFlags } = useQuery({
    queryKey: ["admin", "plans", selectedPlanId, "feature-flags"],
    queryFn: () => fetchPlanFeatureFlags(selectedPlanId as string),
    enabled: !!selectedPlanId,
  });

  const { data: planLimits } = useQuery({
    queryKey: ["admin", "plans", selectedPlanId, "resource-limits"],
    queryFn: () => fetchPlanResourceLimits(selectedPlanId as string),
    enabled: !!selectedPlanId,
  });

  const createMutation = useMutation({
    mutationFn: () => createPlan(createForm),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "plans"] });
      setCreateOpen(false);
      setCreateForm({ key: "", name: "", is_default: false });
      setCreateError(null);
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setCreateError(axiosErr.response?.data?.detail ?? "Failed to create plan.");
    },
  });

  const toggleDefaultMutation = useMutation({
    mutationFn: ({ planId, isDefault }: { planId: string; isDefault: boolean }) =>
      updatePlan(planId, { is_default: isDefault }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "plans"] }),
  });

  const saveFlagsMutation = useMutation({
    mutationFn: () =>
      setPlanFeatureFlags(
        selectedPlanId as string,
        Object.entries(pendingFlagEdits).map(([feature_flag_id, enabled]) => ({ feature_flag_id, enabled })),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "plans", selectedPlanId, "feature-flags"] });
      setPendingFlagEdits({});
    },
  });

  const saveLimitsMutation = useMutation({
    mutationFn: () =>
      setPlanResourceLimits(
        selectedPlanId as string,
        Object.entries(pendingLimitEdits).map(([resource_key, value]) => ({
          resource_key,
          max_count: value.trim() === "" ? null : Number(value),
        })),
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "plans", selectedPlanId, "resource-limits"] });
      setPendingLimitEdits({});
    },
  });

  const selectedPlan = plans?.find((p) => p.id === selectedPlanId) ?? null;
  const enabledByFlagId = new Map((planFlags ?? []).map((f) => [f.feature_flag_id, f.enabled]));

  function isFlagEnabled(flagId: string): boolean {
    if (flagId in pendingFlagEdits) return pendingFlagEdits[flagId];
    return enabledByFlagId.get(flagId) ?? false;
  }

  function limitInputValue(resourceKey: string, maxCount: number | null): string {
    if (resourceKey in pendingLimitEdits) return pendingLimitEdits[resourceKey];
    return maxCount === null ? "" : String(maxCount);
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Plans</h1>
          <p className="text-sm text-muted-foreground">
            Billing/entitlement tiers. A tenant's plan sits between its own feature-flag override and the
            flag's global default in the resolution order.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" />
          New plan
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All plans</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>}
          {isError && <p className="py-8 text-center text-sm text-destructive">Could not load plans.</p>}
          {!isLoading && !isError && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Key</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Default</TableHead>
                  <TableHead className="w-40" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(plans ?? []).map((plan) => (
                  <TableRow key={plan.id}>
                    <TableCell className="font-mono text-sm font-medium text-foreground">{plan.key}</TableCell>
                    <TableCell>{plan.name}</TableCell>
                    <TableCell>
                      <Badge variant={plan.is_default ? "success" : "secondary"}>
                        {plan.is_default ? "Default" : "—"}
                      </Badge>
                    </TableCell>
                    <TableCell className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => toggleDefaultMutation.mutate({ planId: plan.id, isDefault: !plan.is_default })}
                      >
                        {plan.is_default ? "Unset default" : "Make default"}
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => {
                          setSelectedPlanId(plan.id === selectedPlanId ? null : plan.id);
                          setPendingFlagEdits({});
                        }}
                      >
                        {plan.id === selectedPlanId ? "Hide flags" : "Feature flags"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {(plans ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                      No plans yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {selectedPlan && (
        <Card>
          <CardHeader>
            <CardTitle>Feature flags for {selectedPlan.name}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <div className="flex flex-col gap-2">
              {(allFlags ?? []).map((flag) => (
                <label
                  key={flag.id}
                  className="flex items-center gap-3 rounded-md border border-border p-3 text-sm"
                >
                  <input
                    type="checkbox"
                    checked={isFlagEnabled(flag.id)}
                    onChange={(e) =>
                      setPendingFlagEdits((edits) => ({ ...edits, [flag.id]: e.target.checked }))
                    }
                  />
                  <span className="flex-1 font-mono">{flag.key}</span>
                  {flag.description && <span className="text-xs text-muted-foreground">{flag.description}</span>}
                </label>
              ))}
              {(allFlags ?? []).length === 0 && (
                <p className="py-4 text-center text-sm text-muted-foreground">No feature flags defined yet.</p>
              )}
            </div>
            <div className="flex justify-end">
              <Button
                onClick={() => saveFlagsMutation.mutate()}
                disabled={Object.keys(pendingFlagEdits).length === 0 || saveFlagsMutation.isPending}
              >
                Save changes
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {selectedPlan && (
        <Card>
          <CardHeader>
            <CardTitle>Resource limits for {selectedPlan.name}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <p className="text-xs text-muted-foreground">
              Leave blank for unlimited. A tenant-specific override (set on the tenant's detail page)
              always beats this plan default.
            </p>
            <div className="flex flex-col gap-2">
              {(planLimits ?? []).map((limit) => (
                <div
                  key={limit.connector_type_id}
                  className="flex items-center gap-3 rounded-md border border-border p-3 text-sm"
                >
                  <span className="flex-1 font-mono">{limit.resource_key}</span>
                  <span className="text-xs text-muted-foreground">{limit.display_name}</span>
                  <Input
                    type="number"
                    min={0}
                    placeholder="Unlimited"
                    className="h-9 w-28"
                    value={limitInputValue(limit.resource_key, limit.max_count)}
                    onChange={(e) =>
                      setPendingLimitEdits((edits) => ({ ...edits, [limit.resource_key]: e.target.value }))
                    }
                  />
                </div>
              ))}
              {(planLimits ?? []).length === 0 && (
                <p className="py-4 text-center text-sm text-muted-foreground">No limitable resources found.</p>
              )}
            </div>
            <div className="flex justify-end">
              <Button
                onClick={() => saveLimitsMutation.mutate()}
                disabled={Object.keys(pendingLimitEdits).length === 0 || saveLimitsMutation.isPending}
              >
                Save changes
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New plan"
        description="Key is immutable once created."
      >
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
        >
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="plan-key">
              Key
            </label>
            <Input
              id="plan-key"
              placeholder="e.g. pro"
              value={createForm.key}
              onChange={(e) => setCreateForm((f) => ({ ...f, key: e.target.value }))}
              required
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="plan-name">
              Name
            </label>
            <Input
              id="plan-name"
              placeholder="e.g. Pro"
              value={createForm.name}
              onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
              required
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={createForm.is_default}
              onChange={(e) => setCreateForm((f) => ({ ...f, is_default: e.target.checked }))}
            />
            Make this the default plan
          </label>
          {createError && <p className="text-sm text-destructive">{createError}</p>}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              Create
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
