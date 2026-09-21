import { useMemo, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { AxiosError } from "axios";
import { Button, Input, Textarea } from "@fusion-flow/ui";
import { useConnectorInstances } from "../../../connectors/hooks";
import { WizardShell, SummarySidebar, TipsCallout } from "../../wizard";
import { useCreateCampaign } from "../hooks";

const STEPS = ["Message", "Schedule"];

const TIPS = [
  "This is a one-time send — for a recurring campaign, use the full Workflow builder instead.",
  "Each recipient must have previously messaged your WhatsApp number within Meta's messaging window, or the message must use an approved template (this campaign sends plain text).",
];

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

  const whatsappInstance = useMemo(
    () =>
      connectorInstances.find(
        (instance) => instance.connector_type_key === "whatsapp" && instance.state === "connected",
      ),
    [connectorInstances],
  );

  const recipients = useMemo(() => parseRecipients(recipientsRaw), [recipientsRaw]);

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
      setStepError("Add at least one recipient phone number.");
      return;
    }
    setStepError(null);
    setCurrentStepIndex(1);
  }

  function handleCreate() {
    if (!whatsappInstance) return;

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
        connector_instance_id: whatsappInstance.id,
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
          { label: "Recipients", value: recipients.length > 0 ? `${recipients.length} recipient(s)` : "" },
          { label: "Scheduled For", value: scheduledForSummary },
        ]}
      />
      <TipsCallout tips={TIPS} />
    </>
  );

  if (isLoadingConnectors) {
    return (
      <WizardShell title="New Broadcast Campaign" backTo="/communication/broadcasts">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </WizardShell>
    );
  }

  if (!whatsappInstance) {
    return (
      <WizardShell title="New Broadcast Campaign" backTo="/communication/broadcasts">
        <p className="text-sm text-foreground">
          Broadcast campaigns send over WhatsApp, and you don't have a connected WhatsApp number yet.
        </p>
        <p className="text-sm text-muted-foreground">
          Connect WhatsApp first, then come back here to create a campaign.
        </p>
        <Link to="/connectors/whatsapp/connect">
          <Button className="mt-2">Connect WhatsApp</Button>
        </Link>
      </WizardShell>
    );
  }

  return (
    <WizardShell
      title="New Broadcast Campaign"
      description="Send a one-time scheduled WhatsApp message to a list of recipients."
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
              Recipients
            </label>
            <Textarea
              id="campaign-recipients"
              rows={6}
              value={recipientsRaw}
              onChange={(event) => setRecipientsRaw(event.target.value)}
              placeholder={"+15550001234\n+15550005678"}
            />
            <p className="text-xs text-muted-foreground">
              One phone number per line, or separate with commas. Include country code, e.g. +15550001234.
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
