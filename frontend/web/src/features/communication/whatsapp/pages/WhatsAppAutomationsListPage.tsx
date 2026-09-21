import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bot, Pencil, Plus, Trash2 } from "lucide-react";
import { Button, Card, CardContent, CardHeader, CardTitle } from "@fusion-flow/ui";
import { Switch } from "../../wizard";
import { ConfirmDialog } from "../../../connectors/components/ConfirmDialog";
import {
  useDeleteWhatsAppAutomation,
  useSetWhatsAppAutomationActive,
  useWhatsAppAutomations,
} from "../hooks";

/**
 * `/communication/whatsapp/automations` - list of every WhatsApp
 * predefined automation the tenant has configured (today, just
 * "Appointment Booking"), each togglable active/paused in place and
 * editable/deletable, mirroring the loading/empty-state visual pattern
 * used by `features/connectors/pages/ConnectorsGridPage.tsx`.
 */
export function WhatsAppAutomationsListPage() {
  const navigate = useNavigate();
  const { data: automations, isLoading } = useWhatsAppAutomations();
  const setActiveMutation = useSetWhatsAppAutomationActive();
  const deleteMutation = useDeleteWhatsAppAutomation();
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  const pendingAutomation = (automations ?? []).find((a) => a.id === pendingDeleteId);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">WhatsApp Automations</h1>
          <p className="text-sm text-muted-foreground">
            Predefined automations that react to inbound WhatsApp messages - no workflow canvas required.
          </p>
        </div>
        <Button onClick={() => navigate("/communication/whatsapp/automations/new")}>
          <Plus className="h-4 w-4" />
          New Automation
        </Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading automations…</p>
      ) : (automations ?? []).length === 0 ? (
        <Card>
          <CardHeader className="items-center text-center">
            <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft text-accent">
              <Bot className="h-6 w-6" />
            </div>
            <CardTitle>No automations yet</CardTitle>
            <p className="text-sm text-muted-foreground">
              Set up appointment booking so WhatsApp messages with the right keyword automatically get
              acknowledged and raised as a ticket for your team.
            </p>
            <Button className="mt-2" onClick={() => navigate("/communication/whatsapp/automations/new")}>
              <Plus className="h-4 w-4" />
              New Automation
            </Button>
          </CardHeader>
        </Card>
      ) : (
        <div className="flex flex-col gap-3">
          {(automations ?? []).map((automation) => (
            <Card key={automation.id}>
              <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
                <div>
                  <p className="text-sm font-medium text-foreground">{automation.config.service_name}</p>
                  <p className="text-xs text-muted-foreground">
                    Triggers on: {automation.config.trigger_keywords.join(", ")}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <Switch
                      checked={automation.is_active}
                      onCheckedChange={(checked) =>
                        setActiveMutation.mutate({ id: automation.id, isActive: checked })
                      }
                      aria-label={automation.is_active ? "Pause automation" : "Resume automation"}
                    />
                    <span className="text-xs text-muted-foreground">
                      {automation.is_active ? "Active" : "Paused"}
                    </span>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate(`/communication/whatsapp/automations/${automation.id}/edit`)}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                    Edit
                  </Button>
                  <Button variant="destructive" size="sm" onClick={() => setPendingDeleteId(automation.id)}>
                    <Trash2 className="h-3.5 w-3.5" />
                    Delete
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={pendingDeleteId !== null}
        title={`Delete ${pendingAutomation?.config.service_name ?? "this automation"}?`}
        description="This stops matching new WhatsApp messages against this automation. This can't be undone."
        confirmLabel="Delete"
        destructive
        busy={deleteMutation.isPending}
        onCancel={() => setPendingDeleteId(null)}
        onConfirm={() => {
          if (!pendingDeleteId) return;
          deleteMutation.mutate(pendingDeleteId, {
            onSettled: () => setPendingDeleteId(null),
          });
        }}
      />
    </div>
  );
}
