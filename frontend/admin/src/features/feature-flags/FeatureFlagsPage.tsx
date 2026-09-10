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
  createFeatureFlag,
  fetchFeatureFlagCatalog,
  fetchFeatureFlagOverrides,
  fetchFeatureFlags,
  fetchTenants,
  updateFeatureFlag,
  upsertFeatureFlagOverride,
} from "../../lib/endpoints";

/** Sentinel option value for "not one of the known keys - let me type my own". */
const CUSTOM_KEY_OPTION = "__custom__";

export function FeatureFlagsPage() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({ key: "", description: "", is_global_default: false });
  // Tracks which <select> option is chosen, separately from `createForm.key`
  // (the actual value submitted) - lets "Other (custom key)" swap in a free
  // text Input without losing track of which mode we're in.
  const [keySelection, setKeySelection] = useState<string>(CUSTOM_KEY_OPTION);
  const [createError, setCreateError] = useState<string | null>(null);
  const [selectedFlagId, setSelectedFlagId] = useState<string | null>(null);
  const [overrideTenantId, setOverrideTenantId] = useState("");
  const [overrideEnabled, setOverrideEnabled] = useState(true);

  const { data: flags, isLoading, isError } = useQuery({
    queryKey: ["admin", "feature-flags"],
    queryFn: fetchFeatureFlags,
  });

  const { data: catalog } = useQuery({
    queryKey: ["admin", "feature-flags", "catalog"],
    queryFn: fetchFeatureFlagCatalog,
  });

  // Known keys that don't already have a flag row yet - no point offering
  // one that would just 409 on create.
  const existingKeys = new Set((flags ?? []).map((f) => f.key));
  const availableCatalogEntries = (catalog ?? []).filter((entry) => !existingKeys.has(entry.key));
  const selectedCatalogEntry = availableCatalogEntries.find((entry) => entry.key === keySelection);

  const { data: tenants } = useQuery({ queryKey: ["admin", "tenants"], queryFn: fetchTenants });

  const { data: overrides } = useQuery({
    queryKey: ["admin", "feature-flags", selectedFlagId, "overrides"],
    queryFn: () => fetchFeatureFlagOverrides(selectedFlagId as string),
    enabled: !!selectedFlagId,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      createFeatureFlag({
        key: createForm.key,
        description: createForm.description || null,
        is_global_default: createForm.is_global_default,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["admin", "feature-flags"] });
      setCreateOpen(false);
      setCreateForm({ key: "", description: "", is_global_default: false });
      setKeySelection(CUSTOM_KEY_OPTION);
      setCreateError(null);
    },
    onError: (err) => {
      const axiosErr = err as AxiosError<{ detail?: string }>;
      setCreateError(axiosErr.response?.data?.detail ?? "Failed to create feature flag.");
    },
  });

  const toggleDefaultMutation = useMutation({
    mutationFn: ({ flagId, isGlobalDefault }: { flagId: string; isGlobalDefault: boolean }) =>
      updateFeatureFlag(flagId, { is_global_default: isGlobalDefault }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "feature-flags"] }),
  });

  const overrideMutation = useMutation({
    mutationFn: () =>
      upsertFeatureFlagOverride(selectedFlagId as string, {
        tenant_id: overrideTenantId || null,
        enabled: overrideEnabled,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["admin", "feature-flags", selectedFlagId, "overrides"],
      });
      setOverrideTenantId("");
    },
  });

  const selectedFlag = flags?.find((f) => f.id === selectedFlagId) ?? null;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Feature flags</h1>
          <p className="text-sm text-muted-foreground">
            Tenant override beats the flag's own global override, which beats its platform default.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" />
          New flag
        </Button>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>All flags</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading && <p className="py-8 text-center text-sm text-muted-foreground">Loading…</p>}
          {isError && (
            <p className="py-8 text-center text-sm text-destructive">Could not load feature flags.</p>
          )}
          {!isLoading && !isError && (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Key</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Global default</TableHead>
                  <TableHead className="w-32" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(flags ?? []).map((flag) => (
                  <TableRow key={flag.id}>
                    <TableCell className="font-mono text-sm font-medium text-foreground">
                      {flag.key}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{flag.description ?? "—"}</TableCell>
                    <TableCell>
                      <Badge variant={flag.is_global_default ? "success" : "secondary"}>
                        {flag.is_global_default ? "Enabled" : "Disabled"}
                      </Badge>
                    </TableCell>
                    <TableCell className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() =>
                          toggleDefaultMutation.mutate({
                            flagId: flag.id,
                            isGlobalDefault: !flag.is_global_default,
                          })
                        }
                      >
                        Toggle default
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setSelectedFlagId(flag.id === selectedFlagId ? null : flag.id)}
                      >
                        {flag.id === selectedFlagId ? "Hide overrides" : "Overrides"}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {(flags ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="py-8 text-center text-sm text-muted-foreground">
                      No feature flags yet.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {selectedFlag && (
        <Card>
          <CardHeader>
            <CardTitle>Overrides for {selectedFlag.key}</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Scope</TableHead>
                  <TableHead>Enabled</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(overrides ?? []).map((o) => (
                  <TableRow key={o.id}>
                    <TableCell className="font-mono text-xs">
                      {o.tenant_id ? `tenant: ${o.tenant_id}` : "global override"}
                    </TableCell>
                    <TableCell>
                      <Badge variant={o.enabled ? "success" : "destructive"}>
                        {o.enabled ? "On" : "Off"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
                {(overrides ?? []).length === 0 && (
                  <TableRow>
                    <TableCell colSpan={2} className="py-6 text-center text-sm text-muted-foreground">
                      No overrides set - resolves to the platform default above.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>

            <div className="flex flex-wrap items-end gap-3 border-t border-border pt-4">
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-muted-foreground" htmlFor="override-tenant">
                  Tenant (blank = global override)
                </label>
                <select
                  id="override-tenant"
                  className="h-10 w-64 rounded-md border border-input bg-card px-3 text-sm text-foreground"
                  value={overrideTenantId}
                  onChange={(e) => setOverrideTenantId(e.target.value)}
                >
                  <option value="">Global override</option>
                  {(tenants ?? []).map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-muted-foreground" htmlFor="override-enabled">
                  Enabled
                </label>
                <select
                  id="override-enabled"
                  className="h-10 w-32 rounded-md border border-input bg-card px-3 text-sm text-foreground"
                  value={overrideEnabled ? "true" : "false"}
                  onChange={(e) => setOverrideEnabled(e.target.value === "true")}
                >
                  <option value="true">On</option>
                  <option value="false">Off</option>
                </select>
              </div>
              <Button onClick={() => overrideMutation.mutate()} disabled={overrideMutation.isPending}>
                Save override
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Modal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="New feature flag"
        description="Key is immutable once created (matches the backend's unique catalog key)."
      >
        <form
          className="flex flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            createMutation.mutate();
          }}
        >
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="flag-key-select">
              Key
            </label>
            <select
              id="flag-key-select"
              className="h-10 rounded-md border border-input bg-card px-3 text-sm text-foreground"
              value={keySelection}
              onChange={(e) => {
                const value = e.target.value;
                setKeySelection(value);
                if (value === CUSTOM_KEY_OPTION) {
                  setCreateForm((f) => ({ ...f, key: "" }));
                  return;
                }
                const entry = availableCatalogEntries.find((c) => c.key === value);
                setCreateForm((f) => ({
                  ...f,
                  key: value,
                  description: entry?.description ?? f.description,
                }));
              }}
            >
              {availableCatalogEntries.map((entry) => (
                <option key={entry.key} value={entry.key}>
                  {entry.label} ({entry.key})
                </option>
              ))}
              <option value={CUSTOM_KEY_OPTION}>Other (custom key)…</option>
            </select>
            {selectedCatalogEntry && (
              <p className="text-xs text-muted-foreground">
                {selectedCatalogEntry.gates_real_behavior
                  ? "Already wired to real behavior in the app."
                  : "Reserved for future use - not wired to any behavior yet."}
              </p>
            )}
            {keySelection === CUSTOM_KEY_OPTION && (
              <Input
                id="flag-key"
                placeholder="e.g. advanced_workflows"
                value={createForm.key}
                onChange={(e) => setCreateForm((f) => ({ ...f, key: e.target.value }))}
                required
              />
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-sm font-medium" htmlFor="flag-description">
              Description
            </label>
            <Input
              id="flag-description"
              placeholder="What this flag gates"
              value={createForm.description}
              onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={createForm.is_global_default}
              onChange={(e) => setCreateForm((f) => ({ ...f, is_global_default: e.target.checked }))}
            />
            Enabled by default for every tenant
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
