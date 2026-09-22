import { useEffect, useMemo, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AxiosError } from "axios";
import { Button, Input, Textarea } from "@fusion-flow/ui";
import { useConnectorInstances } from "../../../connectors/hooks";
import type { ConnectorInstance } from "../../../connectors/types";
import { WizardShell, SummarySidebar, TipsCallout, OptionPickerCard } from "../../wizard";
import { useCreateCampaign } from "../hooks";

const STEPS = ["Message", "Schedule"];

/** Connector types a broadcast campaign can currently send over. */
const BROADCASTABLE_CONNECTOR_TYPES = new Set(["whatsapp", "instagram"]);

const BASE_TIPS = [
  "This is a one-time send — for a recurring campaign, use the full Workflow builder instead.",
];

const WHATSAPP_TIP =
  "Each recipient must have previously messaged your WhatsApp number within Meta's messaging window, or the message must use an approved template (this campaign sends plain text).";

const INSTAGRAM_TIP =
  "Instagram only allows messaging a recipient within 24 hours of their last message to you — recipients outside that window will be skipped, not sent to.";

/** Splits a comma/newline separated block of phone numbers into a clean
 * list - trims whitespace and drops empty entries, per this page's
 * "One phone number per line, or separate with commas" helper text. */
function parseRecipients(raw: string): string[] {
  return raw
    .split(/[\n,]/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
}

/** `/communication/broadcasts/new`. Creation only - the backend has no
 * update endpoint for a campaign, so there is no edit mode; a tenant who
 * needs to change something deletes and recreates, matching this
 * codebase's established "immutable after creation" convention (see
 * `custom_fields.schemas.FieldDefinitionUpdate`'s docstring). */
export function BroadcastCampaignWizardPage() {
  const navigate = useNavigate();
  const { data: connectorInstances = [], isLoading: isLoadingConnectors } = useConnectorInstances();
  const createMutation = useCreateCampaign();

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [name, setName] = useState("");
  const [messageText, setMessageText] = useState("");
  const [recipientsRaw, setRecipientsRaw] = useState("");
  const [scheduledAtLocal, setScheduledAtLocal] = useState("");
  const [stepError, setStepError] = useState<string | null>(null);

  const channelInstances = useMemo(
    () =>
      connectorInstances.filter(
        (instance) => BROADCASTABLE_CONNECTOR_TYPES.has(instance.connector_type_key) && instance.state === "connected",
      ),
    [connectorInstances],
  );

  const [selectedInstanceId, setSelectedInstanceId] = useState<string | null>(null);

  // Auto-select the only connected channel, or the first one once the list
  // loads - the tenant only has to pick explicitly when there's more than one.
  useEffect(() => {
    if (channelInstances.length === 0) {
      setSelectedInstanceId(null);
      return;
    }
    setSelectedInstanceId((current) => {
      if (current && channelInstances.some((instance) => instance.id === current)) {
        return current;
      }
      return channelInstances[0].id;
    });
  }, [channelInstances]);

  const selectedInstance: ConnectorInstance | undefined = useMemo(
    () => channelInstances.find((instance) => instance.id === selectedInstanceId),
    [channelInstances, selectedInstanceId],
  );

  const isInstagram = selectedInstance?.connector_type_key === "instagram";

  const recipients = useMemo(() => parseRecipients(recipientsRaw), [recipientsRaw]);

  const tips = useMemo(() => {
    if (isInstagram) return [...BASE_TIPS, INSTAGRAM_TIP];
    return [...BASE_TIPS, WHATSAPP_TIP];
  }, [isInstagram]);

  const mutationError = createMutation.error as AxiosError<{ detail?: string }> | null;

  function goToSchedule() {
    if (!name.trim()) {
      setStepError("Campaign name is required.");
      return;
    }
    if (!messageText.trim()) {
      setStepError("Message text is required.");
      return;
    }
    if (recipients.length === 0) {
      setStepError(isInstagram ? "Add at least one recipient Instagram user ID." : "Add at least one recipient phone number.");
      return;
    }
    setStepError(null);
    setCurrentStepIndex(1);
  }

  function handleCreate() {
    if (!selectedInstance) return;

    if (!scheduledAtLocal) {
      setStepError("Pick a date and time to send this campaign.");
      return;
    }
    const scheduledDate = new Date(scheduledAtLocal);
    if (Number.isNaN(scheduledDate.getTime())) {
      setStepError("That date/time is not valid.");
      return;
    }
    if (scheduledDate.getTime() <= Date.now()) {
      setStepError("Scheduled time must be in the future.");
      return;
    }
    setStepError(null);

    createMutation.mutate(
      {
        connector_instance_id: selectedInstance.id,
        name: name.trim(),
        message_text: messageText,
        recipient_phone_numbers: recipients,
        scheduled_at: scheduledDate.toISOString(),
      },
      {
        onSuccess: () => navigate("/communication/broadcasts"),
      },
    );
  }

  const scheduledForSummary = scheduledAtLocal
    ? (() => {
        const parsed = new Date(scheduledAtLocal);
        return Number.isNaN(parsed.getTime()) ? "" : parsed.toLocaleString();
      })()
    : "";

  const sidebar = (
    <>
      <SummarySidebar
        rows={[
          { label: "Campaign Name", value: name },
          {
            label: "Send From",
            value: selectedInstance
              ? `${selectedInstance.connector_type_display_name} — ${selectedInstance.display_name}`
              : "",
          },
          { label: "Recipients", value: recipients.length > 0 ? `${recipients.length} recipient(s)` : "" },
          { label: "Scheduled For", value: scheduledForSummary },
        ]}
      />
      <TipsCallout tips={tips} />
    </>
  );

  if (isLoadingConnectors) {
    return (
      <WizardShell title="New Broadcast Campaign" backTo="/communication/broadcasts">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </WizardShell>
    );
  }

  if (channelInstances.length === 0) {
    return (
      <WizardShell title="New Broadcast Campaign" backTo="/communication/broadcasts">
        <p className="text-sm text-foreground">
          Broadcast campaigns send over WhatsApp or Instagram, and you don't have a connected WhatsApp
          number or Instagram account yet.
        </p>
        <p className="text-sm text-muted-foreground">
          Connect one first, then come back here to create a campaign.
        </p>
        <div className="mt-2 flex gap-2">
          <Link to="/connectors/whatsapp/connect">
            <Button>Connect WhatsApp</Button>
          </Link>
          <Link to="/connectors/instagram/connect">
            <Button variant="outline">Connect Instagram</Button>
          </Link>
        </div>
      </WizardShell>
    );
  }

  return (
    <WizardShell
      title="New Broadcast Campaign"
      description="Send a one-time scheduled message to a list of recipients."
      backTo="/communication/broadcasts"
      steps={STEPS}
      currentStepIndex={currentStepIndex}
      sidebar={sidebar}
      footer={
        currentStepIndex === 0 ? (
          <Button onClick={goToSchedule}>Next</Button>
        ) : (
          <>
            <Button variant="outline" onClick={() => setCurrentStepIndex(0)}>
              Back
            </Button>
            <Button onClick={handleCreate} disabled={createMutation.isPending}>
              {createMutation.isPending ? "Creating…" : "Create Campaign"}
            </Button>
          </>
        )
      }
    >
      {currentStepIndex === 0 && (
        <>
          {channelInstances.length > 1 && (
            <div className="flex flex-col gap-1.5">
              <label className="text-sm font-medium">Send From</label>
              <div className="grid gap-2 sm:grid-cols-2">
                {channelInstances.map((instance) => (
                  <OptionPickerCard
                    key={instance.id}
                    title={instance.connector_type_display_name}
                    description={instance.display_name}
                    selected={instance.id === selectedInstanceId}
                    onSelect={() => setSelectedInstanceId(instance.id)}
                  />
                ))}
              </div>
            </div>
          )}

          <div className="flex flex-col gap-1.5">
            <label htmlFor="campaign-name" className="text-sm font-medium">
              Campaign Name
            </label>
            <Input
              id="campaign-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. September promo blast"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="campaign-message" className="text-sm font-medium">
              Message
            </label>
            <Textarea
              id="campaign-message"
              rows={4}
              value={messageText}
              onChange={(event) => setMessageText(event.target.value)}
              placeholder="What should this campaign send?"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="campaign-recipients" className="text-sm font-medium">
              {isInstagram ? "Recipient Instagram user IDs" : "Recipient phone numbers"}
            </label>
            <Textarea
              id="campaign-recipients"
              rows={6}
              value={recipientsRaw}
              onChange={(event) => setRecipientsRaw(event.target.value)}
              placeholder={isInstagram ? "17841400000000001\n17841400000000002" : "+15550001234\n+15550005678"}
            />
            <p className="text-xs text-muted-foreground">
              {isInstagram
                ? "One Instagram-scoped user ID per line, or separate with commas."
                : "One phone number per line, or separate with commas. Include country code, e.g. +15550001234."}
            </p>
            {recipients.length > 0 && (
              <p className="text-xs text-muted-foreground">{recipients.length} recipient(s) detected.</p>
            )}
          </div>
        </>
      )}

      {currentStepIndex === 1 && (
        <div className="flex flex-col gap-1.5">
          <label htmlFor="campaign-scheduled-at" className="text-sm font-medium">
            Send At
          </label>
          <Input
            id="campaign-scheduled-at"
            type="datetime-local"
            value={scheduledAtLocal}
            onChange={(event) => setScheduledAtLocal(event.target.value)}
          />
          <p className="text-xs text-muted-foreground">
            The campaign sends automatically at this date and time. Must be in the future.
          </p>
        </div>
      )}

      {stepError && <p className="text-sm text-destructive">{stepError}</p>}

      {mutationError && (
        <p className="text-sm text-destructive">
          {mutationError.response?.data?.detail ?? "Could not create this campaign."}
        </p>
      )}
    </WizardShell>
  );
}
