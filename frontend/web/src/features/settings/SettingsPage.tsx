import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle, Lock, MessageSquareOff, Plus, ShieldAlert, Users } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
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
import { useAuthStore } from "../../lib/auth-store";
import { listBusinessTemplates } from "../onboarding/business-templates-api";
import { ClinicSchedulingCard } from "./components/ClinicSchedulingCard";
import { SidebarCustomizationCard } from "./components/SidebarCustomizationCard";
import { TeamPermissionsCard } from "./components/TeamPermissionsCard";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { createMember, fetchMembers, updateBusinessSettings, updateMemberIsDoctor } from "./api";
import type { Member } from "./types";

function titleCase(value: string): string {
  return value.replace(/[_-]+/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

const profileSchema = z.object({
  name: z.string().min(1, "Business name is required"),
  vertical: z.string().min(1, "Choose a vertical"),
});
type ProfileFormValues = z.infer<typeof profileSchema>;

const addMemberSchema = z.object({
  email: z.string().email("Enter a valid email address"),
  password: z.string().min(8, "At least 8 characters"),
  role: z.enum(["admin", "member", "viewer"]),
  is_doctor: z.boolean(),
});
type AddMemberFormValues = z.infer<typeof addMemberSchema>;

/**
 * `/settings` — business profile, messaging kill switch, team members
 * (add/edit), and a danger-zone placeholder. Adding a member sets their
 * password directly (there's no transactional-email infrastructure in
 * this app for a real invite-link flow) - the caller shares it with the
 * new member out-of-band. Business deletion is still out of scope here.
 */
export function SettingsPage() {
  const claims = useAuthStore((s) => s.claims);
  const business = useAuthStore((s) => s.business);
  const setBusiness = useAuthStore((s) => s.setBusiness);
  const businessId = claims?.tenant_id ?? null;
  const queryClient = useQueryClient();
  // Business profile, messaging kill switch, team members, and team
  // permissions are ALL owner/admin-only on the backend (require_role) - a
  // Member/Viewer/doctor's underlying requests would already 403, but
  // without this check the page would still render the forms/tables/toggles
  // looking fully interactive right up until a save silently fails. Gate
  // the sections themselves instead, so what's on screen matches what the
  // backend will actually allow.
  const canManageBusiness = business?.role === "owner" || business?.role === "admin";
  const isDoctorMutation = useMutation({
    mutationFn: ({ membershipId, isDoctor }: { membershipId: string; isDoctor: boolean }) => {
      if (!businessId) throw new Error("No active business on this session");
      return updateMemberIsDoctor(businessId, membershipId, isDoctor);
    },
    onSuccess: (updated) => {
      queryClient.setQueryData<Member[]>(["settings", "members", businessId], (prev) =>
        prev?.map((m) => (m.id === updated.id ? updated : m)),
      );
    },
  });

  const [confirmPauseOpen, setConfirmPauseOpen] = useState(false);
  const [addMemberOpen, setAddMemberOpen] = useState(false);

  const {
    register: registerAddMember,
    handleSubmit: handleSubmitAddMember,
    reset: resetAddMember,
    formState: { errors: addMemberErrors },
  } = useForm<AddMemberFormValues>({
    resolver: zodResolver(addMemberSchema),
    defaultValues: { email: "", password: "", role: "member", is_doctor: false },
  });

  const createMemberMutation = useMutation({
    mutationFn: (values: AddMemberFormValues) => {
      if (!businessId) throw new Error("No active business on this session");
      return createMember(businessId, values);
    },
    onSuccess: (created) => {
      queryClient.setQueryData<Member[]>(["settings", "members", businessId], (prev) =>
        prev ? [...prev, created] : [created],
      );
      resetAddMember();
      setAddMemberOpen(false);
    },
  });

  // Derived from the real, admin-extensible BusinessTemplate catalog
  // (the same one onboarding's "pick a starter kit" step already reads)
  // rather than a hardcoded list - a business assigned any vertical an
  // admin has since added a template for would otherwise have no matching
  // <option> and silently render blank. The business's own current
  // `vertical` is always included even if no template uses it (e.g. it
  // was set before that template existed, or free-typed some other way),
  // so the field never shows blank for a value that IS genuinely set.
  const { data: businessTemplates = [] } = useQuery({
    queryKey: ["settings", "business-templates"],
    queryFn: listBusinessTemplates,
  });
  const verticals = (() => {
    const seen = new Map<string, string>();
    for (const template of businessTemplates) {
      if (template.vertical) seen.set(template.vertical, titleCase(template.vertical));
    }
    if (business?.vertical && !seen.has(business.vertical)) {
      seen.set(business.vertical, titleCase(business.vertical));
    }
    return [...seen.entries()].map(([value, label]) => ({ value, label }));
  })();

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: { name: business?.name ?? "", vertical: business?.vertical ?? "" },
  });

  useEffect(() => {
    reset({ name: business?.name ?? "", vertical: business?.vertical ?? "" });
  }, [business?.name, business?.vertical, reset]);

  const profileMutation = useMutation({
    mutationFn: (values: ProfileFormValues) => {
      if (!businessId) throw new Error("No active business on this session");
      return updateBusinessSettings(businessId, { name: values.name, vertical: values.vertical });
    },
    onSuccess: (updated) => setBusiness(updated),
  });

  const killSwitchMutation = useMutation({
    mutationFn: (messaging_paused: boolean) => {
      if (!businessId) throw new Error("No active business on this session");
      return updateBusinessSettings(businessId, { messaging_paused });
    },
    onSuccess: (updated) => {
      setBusiness(updated);
      setConfirmPauseOpen(false);
    },
  });

  const messagingPaused = business?.messaging_paused ?? false;

  function handleToggleMessaging() {
    if (messagingPaused) {
      // Turning back on needs no confirmation.
      killSwitchMutation.mutate(false);
    } else {
      setConfirmPauseOpen(true);
    }
  }

  const {
    data: members = [],
    isLoading: membersLoading,
    isError: membersError,
  } = useQuery({
    queryKey: ["settings", "members", businessId],
    queryFn: () => fetchMembers(businessId as string),
    enabled: !!businessId && canManageBusiness,
  });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Manage your business profile, messaging automation, and team.
        </p>
      </div>

      {!canManageBusiness && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Lock className="h-5 w-5" />
              Limited settings access
            </CardTitle>
            <CardDescription>
              Your role ({business?.role ?? "member"}) can't view or change business profile,
              messaging, team members, or team permissions. Ask an owner or admin if you need
              something changed here.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* Profile */}
      {canManageBusiness && (
      <Card>
        <CardHeader>
          <CardTitle>Business profile</CardTitle>
          <CardDescription>Your business name and vertical, used across the app.</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="flex flex-col gap-4"
            onSubmit={handleSubmit((values) => profileMutation.mutate(values))}
            noValidate
          >
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="flex flex-col gap-1.5">
                <label htmlFor="name" className="text-sm font-medium">
                  Business name
                </label>
                <Input id="name" error={!!errors.name} {...register("name")} />
                {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
              </div>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="vertical" className="text-sm font-medium">
                  Vertical
                </label>
                <select
                  id="vertical"
                  className="flex h-10 w-full rounded-md border border-input bg-card px-3 py-2 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  defaultValue={business?.vertical ?? ""}
                  {...register("vertical")}
                >
                  <option value="" disabled>
                    Select a vertical...
                  </option>
                  {verticals.map((v) => (
                    <option key={v.value} value={v.value}>
                      {v.label}
                    </option>
                  ))}
                </select>
                {errors.vertical && <p className="text-xs text-destructive">{errors.vertical.message}</p>}
              </div>
            </div>
            {profileMutation.isError && (
              <p className="text-sm text-destructive">Could not save your business. Please try again.</p>
            )}
            {profileMutation.isSuccess && !profileMutation.isPending && (
              <p className="text-sm text-success">Saved.</p>
            )}
            <div>
              <Button type="submit" disabled={profileMutation.isPending || !businessId}>
                {profileMutation.isPending ? "Saving..." : "Save changes"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
      )}

      {/* Clinic scheduling */}
      <ClinicSchedulingCard businessId={businessId} />

      {/* Messaging kill switch */}
      {canManageBusiness && (
      <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <MessageSquareOff className="h-5 w-5" />
            Messaging kill switch
          </CardTitle>
          <CardDescription>
            Pauses every messaging automation workflow action (e.g. sending WhatsApp messages)
            tenant-wide. Inbound messages and non-messaging actions keep working — this only stops
            outbound sends triggered by your workflows.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between rounded-md border border-border p-4">
            <div>
              <p className="text-sm font-medium text-foreground">
                Messaging automation is currently{" "}
                {messagingPaused ? (
                  <Badge variant="destructive">Paused</Badge>
                ) : (
                  <Badge variant="success">Active</Badge>
                )}
              </p>
              <p className="text-xs text-muted-foreground">
                {messagingPaused
                  ? "All outbound messaging workflow actions are blocked."
                  : "Outbound messaging workflow actions are running normally."}
              </p>
            </div>
            <button
              type="button"
              role="switch"
              aria-checked={messagingPaused}
              aria-label="Toggle messaging kill switch"
              disabled={killSwitchMutation.isPending || !businessId}
              onClick={handleToggleMessaging}
              className={
                "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 " +
                (messagingPaused ? "bg-destructive" : "bg-border")
              }
            >
              <span
                className={
                  "inline-block h-5 w-5 translate-x-0.5 transform rounded-full bg-white transition-transform " +
                  (messagingPaused ? "translate-x-5" : "translate-x-0.5")
                }
              />
            </button>
          </div>
          {killSwitchMutation.isError && (
            <p className="mt-2 text-sm text-destructive">
              Could not update the messaging kill switch. Please try again.
            </p>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmPauseOpen}
        title="Pause all messaging automation?"
        description="This immediately blocks every workflow action that sends an outbound message (e.g. WhatsApp replies) across your entire business, until you turn it back on. Inbound messages will still be received."
        confirmLabel="Pause messaging"
        cancelLabel="Cancel"
        destructive
        busy={killSwitchMutation.isPending}
        onConfirm={() => killSwitchMutation.mutate(true)}
        onCancel={() => setConfirmPauseOpen(false)}
      />
      </>
      )}

      {/* Team members */}
      {canManageBusiness && (
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-4">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Team members
              </CardTitle>
              <CardDescription className="mt-1.5">
                Everyone with access to this business. Mark a member as a doctor to let reception
                assign them patients in Patient Flow - doctors also need to confirm their password
                once per session before opening that module.
              </CardDescription>
            </div>
            <Button
              type="button"
              size="sm"
              onClick={() => setAddMemberOpen((prev) => !prev)}
              disabled={!businessId}
            >
              <Plus className="mr-1.5 h-4 w-4" />
              Add team member
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {addMemberOpen && (
            <form
              className="mb-6 flex flex-col gap-4 rounded-md border border-border p-4"
              onSubmit={handleSubmitAddMember((values) => createMemberMutation.mutate(values))}
              noValidate
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="new-member-email" className="text-sm font-medium">
                    Email
                  </label>
                  <Input
                    id="new-member-email"
                    type="email"
                    autoComplete="off"
                    error={!!addMemberErrors.email}
                    {...registerAddMember("email")}
                  />
                  {addMemberErrors.email && (
                    <p className="text-xs text-destructive">{addMemberErrors.email.message}</p>
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="new-member-password" className="text-sm font-medium">
                    Temporary password
                  </label>
                  <Input
                    id="new-member-password"
                    type="text"
                    autoComplete="off"
                    error={!!addMemberErrors.password}
                    {...registerAddMember("password")}
                  />
                  {addMemberErrors.password && (
                    <p className="text-xs text-destructive">{addMemberErrors.password.message}</p>
                  )}
                  <p className="text-xs text-muted-foreground">
                    Share this with them yourself - there's no invite email.
                  </p>
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="new-member-role" className="text-sm font-medium">
                    Role
                  </label>
                  <select
                    id="new-member-role"
                    className="h-9 rounded-md border border-input bg-background px-3 text-sm"
                    {...registerAddMember("role")}
                  >
                    <option value="member">Member</option>
                    <option value="admin">Admin</option>
                    <option value="viewer">Viewer</option>
                  </select>
                </div>
                <div className="flex items-end gap-2 pb-1.5">
                  <input
                    id="new-member-is-doctor"
                    type="checkbox"
                    className="h-4 w-4 rounded border-input accent-accent"
                    {...registerAddMember("is_doctor")}
                  />
                  <label htmlFor="new-member-is-doctor" className="text-sm font-medium">
                    This person is a doctor
                  </label>
                </div>
              </div>
              {createMemberMutation.isError && (
                <p className="text-sm text-destructive">
                  Could not add that team member - the email may already be registered.
                </p>
              )}
              <div className="flex gap-2">
                <Button type="submit" disabled={createMemberMutation.isPending}>
                  {createMemberMutation.isPending ? "Adding..." : "Add member"}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    resetAddMember();
                    setAddMemberOpen(false);
                  }}
                >
                  Cancel
                </Button>
              </div>
            </form>
          )}
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Invited</TableHead>
                <TableHead>Accepted</TableHead>
                <TableHead>Doctor</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {membersLoading && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    Loading...
                  </TableCell>
                </TableRow>
              )}
              {membersError && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-destructive">
                    Could not load team members.
                  </TableCell>
                </TableRow>
              )}
              {!membersLoading && !membersError && members.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-muted-foreground">
                    No team members yet.
                  </TableCell>
                </TableRow>
              )}
              {members.map((member) => {
                const pending =
                  isDoctorMutation.isPending && isDoctorMutation.variables?.membershipId === member.id;
                return (
                  <TableRow key={member.id}>
                    <TableCell className="font-medium text-foreground">{member.email}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{member.role}</Badge>
                    </TableCell>
                    <TableCell>{new Date(member.invited_at).toLocaleDateString()}</TableCell>
                    <TableCell>
                      {member.accepted_at ? (
                        new Date(member.accepted_at).toLocaleDateString()
                      ) : (
                        <span className="text-muted-foreground">Pending</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={member.is_doctor}
                        aria-label={`Mark ${member.email} as a doctor`}
                        disabled={pending}
                        onClick={() =>
                          isDoctorMutation.mutate({ membershipId: member.id, isDoctor: !member.is_doctor })
                        }
                        className={
                          "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 " +
                          (member.is_doctor ? "bg-accent" : "bg-border")
                        }
                      >
                        <span
                          className={
                            "inline-block h-5 w-5 translate-x-0.5 transform rounded-full bg-white transition-transform " +
                            (member.is_doctor ? "translate-x-5" : "translate-x-0.5")
                          }
                        />
                      </button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {isDoctorMutation.isError && (
            <p className="mt-2 text-sm text-destructive">Could not update that member. Please try again.</p>
          )}
        </CardContent>
      </Card>
      )}

      {/* Team permissions */}
      {canManageBusiness && <TeamPermissionsCard />}

      {/* Sidebar customization */}
      <SidebarCustomizationCard />

      {/* Danger zone */}
      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-destructive">
            <ShieldAlert className="h-5 w-5" />
            Danger zone
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between gap-4 rounded-md border border-destructive/40 bg-destructive/5 p-4">
            <div className="flex items-start gap-3">
              <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-destructive" />
              <div>
                <p className="text-sm font-medium text-foreground">Delete this business</p>
                <p className="text-xs text-muted-foreground">
                  Business deletion is not available yet — contact support. This is a highly
                  destructive, hard-to-reverse action affecting every record in your account, and
                  needs its own approved confirmation/export/grace-period design before it ships.
                </p>
              </div>
            </div>
            <Button variant="destructive" disabled>
              Delete business
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
