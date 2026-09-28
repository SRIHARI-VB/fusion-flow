import { ShieldQuestion } from "lucide-react";
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
import type { RestrictableRole } from "../../connectors/types";

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

  function toggle(connectorTypeId: string, role: RestrictableRole, currentlyRestricted: boolean) {
    setRestriction.mutate({ connector_type_id: connectorTypeId, role, restricted: !currentlyRestricted });
  }

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
                  Your business doesn't have any restrictable modules yet.
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
                    onClick={() => toggle(module.connector_type_id, "member", module.member_restricted)}
                  />
                </TableCell>
                <TableCell>
                  <RestrictionToggle
                    checked={!module.viewer_restricted}
                    disabled={setRestriction.isPending}
                    label={`Toggle ${module.display_name} for viewers`}
                    onClick={() => toggle(module.connector_type_id, "viewer", module.viewer_restricted)}
                  />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {setRestriction.isError && (
          <p className="mt-2 text-sm text-destructive">Could not update that permission. Please try again.</p>
        )}
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
