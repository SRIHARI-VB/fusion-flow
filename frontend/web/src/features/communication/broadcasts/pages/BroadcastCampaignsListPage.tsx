import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Megaphone, Plus, Trash2 } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  type BadgeVariant,
} from "@fusion-flow/ui";
import { ConfirmDialog } from "../../../connectors/components/ConfirmDialog";
import { useConnectorInstances } from "../../../connectors/hooks";
import { Switch } from "../../wizard";
import { useCampaigns, useDeleteCampaign, useSetCampaignActive } from "../hooks";
import type { BroadcastCampaign } from "../types";

/**
 * Derives a display status for a campaign from its `is_active`/
 * `last_run_status`/`next_run_at` fields - the API has no single
 * "status" field, and there is no separate "sending" state, so a
 * campaign whose scheduled time has passed with no `last_run_status`
 * yet is shown as "Sent" optimistically, per this feature's spec.
 */
function campaignStatus(campaign: BroadcastCampaign): { label: string; variant: BadgeVariant } {
  const { last_run_status, next_run_at, is_active } = campaign;

  if (last_run_status) {
    if (last_run_status === "failed") return { label: "Failed", variant: "destructive" };
    return { label: "Sent", variant: "success" };
  }

  const hasRunTimePassed = next_run_at !== null && new Date(next_run_at).getTime() <= Date.now();
  if (hasRunTimePassed) {
    return { label: "Sent", variant: "success" };
  }

  if (!is_active) {
    return { label: "Paused", variant: "secondary" };
  }

  if (next_run_at) {
    return { label: "Scheduled", variant: "default" };
  }

  return { label: "Paused", variant: "secondary" };
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

/** `/communication/broadcasts` */
export function BroadcastCampaignsListPage() {
  const navigate = useNavigate();
  const { data: campaigns = [], isLoading } = useCampaigns();
  const { data: connectorInstances = [] } = useConnectorInstances();
  const setActiveMutation = useSetCampaignActive();
  const deleteMutation = useDeleteCampaign();
  const [campaignPendingDelete, setCampaignPendingDelete] = useState<BroadcastCampaign | null>(null);

  const isEmpty = !isLoading && campaigns.length === 0;

  /** The campaign DTO only carries `connector_instance_id` - the channel
   * (WhatsApp vs Instagram) it actually sent over is resolved by
   * cross-referencing that id against the tenant's connector instances,
   * rather than adding a `connector_type_key` to the backend DTO. */
  function channelLabelFor(campaign: BroadcastCampaign): string | null {
    const instance = connectorInstances.find((candidate) => candidate.id === campaign.connector_instance_id);
    return instance?.connector_type_display_name ?? null;
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Broadcast Campaigns</h1>
          <p className="text-sm text-muted-foreground">
            Send a one-time scheduled WhatsApp or Instagram message to a list of recipients.
          </p>
        </div>
        <Button onClick={() => navigate("/communication/broadcasts/new")}>
          <Plus className="h-4 w-4" />
          New Campaign
        </Button>
      </div>

      {isEmpty ? (
        <Card className="flex flex-col items-center gap-3 py-16 text-center">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-accent-soft text-accent">
            <Megaphone className="h-7 w-7" />
          </div>
          <p className="text-sm font-medium text-foreground">No campaigns yet</p>
          <p className="max-w-sm text-xs text-muted-foreground">
            Create a broadcast campaign to send a one-time scheduled WhatsApp or Instagram message to a
            list of recipients.
          </p>
          <Button className="mt-2" onClick={() => navigate("/communication/broadcasts/new")}>
            <Plus className="h-4 w-4" />
            New Campaign
          </Button>
        </Card>
      ) : (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Channel</TableHead>
                <TableHead>Recipients</TableHead>
                <TableHead>Next Run</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="w-16">Active</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    Loading...
                  </TableCell>
                </TableRow>
              )}
              {campaigns.map((campaign) => {
                const status = campaignStatus(campaign);
                const channelLabel = channelLabelFor(campaign);
                const isPauseResumeDisabled =
                  setActiveMutation.isPending &&
                  setActiveMutation.variables?.id === campaign.id;
                return (
                  <TableRow key={campaign.id}>
                    <TableCell className="font-medium text-foreground">
                      <span className="flex items-center gap-2">
                        <Megaphone className="h-4 w-4 text-accent" />
                        {campaign.name}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {channelLabel ? <Badge variant="secondary">{channelLabel}</Badge> : "—"}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {campaign.recipient_phone_numbers.length}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatDateTime(campaign.next_run_at)}
                    </TableCell>
                    <TableCell>
                      <Badge variant={status.variant}>{status.label}</Badge>
                    </TableCell>
                    <TableCell>
                      <Switch
                        checked={campaign.is_active}
                        disabled={isPauseResumeDisabled}
                        aria-label={campaign.is_active ? `Pause ${campaign.name}` : `Resume ${campaign.name}`}
                        onCheckedChange={(checked) =>
                          setActiveMutation.mutate({ id: campaign.id, isActive: checked })
                        }
                      />
                    </TableCell>
                    <TableCell>
                      <button
                        type="button"
                        aria-label={`Delete ${campaign.name}`}
                        title="Delete campaign"
                        className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
                        onClick={() => setCampaignPendingDelete(campaign)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      )}

      <ConfirmDialog
        open={campaignPendingDelete !== null}
        title="Delete campaign?"
        description={
          campaignPendingDelete
            ? `"${campaignPendingDelete.name}" will be permanently deleted. This cannot be undone.`
            : undefined
        }
        confirmLabel="Delete"
        destructive
        busy={deleteMutation.isPending}
        onCancel={() => setCampaignPendingDelete(null)}
        onConfirm={() => {
          if (!campaignPendingDelete) return;
          deleteMutation.mutate(campaignPendingDelete.id, {
            onSuccess: () => setCampaignPendingDelete(null),
          });
        }}
      />
    </div>
  );
}
