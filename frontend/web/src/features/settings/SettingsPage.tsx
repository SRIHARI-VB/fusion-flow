import { useEffect, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle, MessageSquareOff, ShieldAlert, Users } from "lucide-react";
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
import { ConfirmDialog } from "./components/ConfirmDialog";
import { fetchMembers, updateBusinessSettings } from "./api";

const VERTICALS = [
  { value: "retail", label: "Retail" },
  { value: "salon", label: "Salon & Beauty" },
  { value: "restaurant", label: "Restaurant" },
  { value: "other", label: "Other" },
];

const profileSchema = z.object({
  name: z.string().min(1, "Business name is required"),
  vertical: z.string().min(1, "Choose a vertical"),
});
type ProfileFormValues = z.infer<typeof profileSchema>;

/**
 * `/settings` — business profile, messaging kill switch, read-only team
 * members, and a danger-zone placeholder. See the plan's "Next
 * Implementation Phase" item 4: invite-flow and business deletion are
 * deliberately out of scope here.
 */
export function SettingsPage() {
  const claims = useAuthStore((s) => s.claims);
  const business = useAuthStore((s) => s.business);
  const setBusiness = useAuthStore((s) => s.setBusiness);
  const businessId = claims?.tenant_id ?? null;

  const [confirmPauseOpen, setConfirmPauseOpen] = useState(false);

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
    enabled: !!businessId,
  });

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6 py-8">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Manage your business profile, messaging automation, and team.
        </p>
      </div>

      {/* Profile */}
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
                  {VERTICALS.map((v) => (
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

      {/* Messaging kill switch */}
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

      {/* Team members */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5" />
            Team members
          </CardTitle>
          <CardDescription>Everyone with access to this business. Read-only for now.</CardDescription>
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
              {membersLoading && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    Loading...
                  </TableCell>
                </TableRow>
              )}
              {membersError && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-destructive">
                    Could not load team members.
                  </TableCell>
                </TableRow>
              )}
              {!membersLoading && !membersError && members.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground">
                    No team members yet.
                  </TableCell>
                </TableRow>
              )}
              {members.map((member) => (
                <TableRow key={member.email}>
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
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

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
