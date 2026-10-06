import { useState } from "react";
import { Info, ShieldQuestion } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@fusion-flow/ui";
import { useModuleRoleAccess, useSetRoleRestriction } from "../../connectors/hooks";
import { ConfirmDialog } from "../../connectors/components/ConfirmDialog";
import { getApiErrorDetail } from "../../../lib/access-events";
import type { ModuleRoleAccess, RestrictableRole } from "../../connectors/types";

/**
 * Owner/Admin-only. Lists every FEATURE module this tenant currently has,
 * with a Member/Viewer restriction toggle per module - unchecked (the
 * default) means that role can see/use it. A module the platform grants
 * this tenant tomorrow shows up here unrestricted automatically (see
 * `RoleModuleRestriction`'s backend docstring): nothing here opts a
 * module IN, rows only ever opt one OUT for one role.
 */
export function TeamPermissionsCard() {
  const { data: modules = [], isLoading, isError } = useModuleRoleAccess();
  const setRestriction = useSetRoleRestriction();

  const [pending, setPending] = useState<{ module: ModuleRoleAccess; role: RestrictableRole } | null>(null);
  const nameByKey = new Map(modules.map((m) => [m.key, m.display_name]));

  function apply(connectorTypeId: string, role: RestrictableRole, currentlyRestricted: boolean) {
    setRestriction.mutate({ connector_type_id: connectorTypeId, role, restricted: !currentlyRestricted });
  }

  function toggle(module: ModuleRoleAccess, role: RestrictableRole, currentlyRestricted: boolean) {
    // Restricting a module others depend on silently degrades those modules
    // for that role (e.g. no customer picker on Orders) - confirm first.
    if (!currentlyRestricted && (module.dependents ?? []).length > 0) {
      setPending({ module, role });
      return;
    }
    apply(module.connector_type_id, role, currentlyRestricted);
  }

  const pendingDependents = (pending?.module.dependents ?? []).map((k) => nameByKey.get(k) ?? k);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldQuestion className="h-5 w-5" />
          Team permissions
        </CardTitle>
        <CardDescription>
          Restrict which modules Member and Viewer roles can see and use. Owner and Admin always have
          full access. A module your business gains access to is visible to everyone by default until
          you restrict it here.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="mb-3 flex items-start gap-2 text-xs text-muted-foreground">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            Owner and Admin are never restricted. Viewer is always read-only (they can look but not
            change anything), even for modules left on. Member is restricted per module using the
            toggles below.
          </span>
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Module</TableHead>
              <TableHead>Member</TableHead>
              <TableHead>Viewer</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  Loading...
                </TableCell>
              </TableRow>
            )}
            {isError && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-destructive">
                  Could not load module permissions.
                </TableCell>
              </TableRow>
            )}
            {!isLoading && !isError && modules.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-muted-foreground">
                  Your business doesn't have any restrictable modules yet. Once the platform enables
                  modules for your business they'll appear here.
                </TableCell>
              </TableRow>
            )}
            {modules.map((module) => (
              <TableRow key={module.connector_type_id}>
                <TableCell className="font-medium text-foreground">{module.display_name}</TableCell>
                <TableCell>
                  <RestrictionToggle
                    checked={!module.member_restricted}
                    disabled={setRestriction.isPending}
                    label={`Toggle ${module.display_name} for members`}
                    onClick={() => toggle(module, "member", module.member_restricted)}
                  />
                </TableCell>
                <TableCell>
                  <RestrictionToggle
                    checked={!module.viewer_restricted}
                    disabled={setRestriction.isPending}
                    label={`Toggle ${module.display_name} for viewers`}
                    onClick={() => toggle(module, "viewer", module.viewer_restricted)}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {setRestriction.isError && (
          <p className="mt-2 text-sm text-destructive">
            {getApiErrorDetail(setRestriction.error, "Could not update that permission. Please try again.")}
          </p>
        )}
        <ConfirmDialog
          open={pending !== null}
          title={`Restrict ${pending?.module.display_name ?? "this module"} for ${pending?.role ?? "this role"}s?`}
          description="Other modules rely on this one, so they will be partly unavailable for that role too."
          confirmLabel="Restrict"
          destructive
          busy={setRestriction.isPending}
          onCancel={() => setPending(null)}
          onConfirm={() => {
            if (!pending) return;
            apply(pending.module.connector_type_id, pending.role, false);
            setPending(null);
          }}
        >
          <ul className="list-disc pl-5 text-sm text-muted-foreground">
            {pendingDependents.map((name) => (
              <li key={name}>{name} - features that use {pending?.module.display_name} (e.g. pickers) will stop working</li>
            ))}
          </ul>
        </ConfirmDialog>
      </CardContent>
    </Card>
  );
}

function RestrictionToggle({
  checked,
  disabled,
  label,
  onClick,
}: {
  checked: boolean;
  disabled: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className={
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 " +
        (checked ? "bg-accent" : "bg-border")
      }
    >
      <span
        className={
          "inline-block h-5 w-5 translate-x-0.5 transform rounded-full bg-white transition-transform " +
          (checked ? "translate-x-5" : "translate-x-0.5")
        }
      />
    </button>
  );
}
