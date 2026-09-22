import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AxiosError } from "axios";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Textarea } from "@fusion-flow/ui";
import { OptionPickerCard, SummarySidebar, TipsCallout, WizardShell } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import { MATCHING_METHOD_DESCRIPTIONS, MATCHING_METHOD_LABELS, MATCHING_METHODS } from "../constants";
import type { InstagramAutomationConfig } from "../types";

const INSTAGRAM_HANDOFF_AUTOMATION_TYPE = "instagram.handoff_automation";

type HandoffMatchingMethod = "exact" | "contains" | "starts_with" | "ends_with";

interface InstagramHandoffAutomationConfig {
  trigger_keywords: string[];
  matching_method: HandoffMatchingMethod;
  ack_text: string;
}

const STEPS = ["Keywords & Matching", "Acknowledgement"];

/** Same "comma-separated field, trim/dedupe/drop-empties" UX as the other
 * Instagram automation wizards - see `InstagramDmAutomationWizardPage.tsx`. */
function parseKeywords(raw: string): string[] {
  return Array.from(
    new Set(
      raw
        .split(",")
        .map((keyword) => keyword.trim())
        .filter((keyword) => keyword.length > 0),
    ),
  );
}

/**
 * `/communication/instagram/handoff-automations/new` and
 * `/communication/instagram/handoff-automations/:id/edit` - the "Human
 * Handoff" wizard: when an inbound DM matches an escalation keyword, send
 * an acknowledgement DM and pause automated replies for that conversation
 * until an agent resumes it from the Inbox. Sibling to
 * `InstagramDmAutomationWizardPage.tsx`, same two-step shape.
 */
export function InstagramHandoffAutomationWizardPage() {
  const { id } = useParams<{ id: string }>();
  const isEditing = Boolean(id);
  const navigate = useNavigate();

  const { data: instances, isLoading: instancesLoading } = useConnectorInstances();
  const { data: automations, isLoading: automationsLoading } = useInstagramAutomations();
  const createMutation = useCreateInstagramAutomation();
  const updateMutation = useUpdateInstagramAutomation();

  const instagramInstance = (instances ?? []).find(
    (instance) => instance.connector_type_key === "instagram" && instance.state === "connected",
  );
  const foundAutomation = isEditing ? automations?.find((automation) => automation.id === id) : undefined;
  const existingAutomation =
    foundAutomation && foundAutomation.automation_type === INSTAGRAM_HANDOFF_AUTOMATION_TYPE
      ? foundAutomation
      : undefined;

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<HandoffMatchingMethod>("contains");
  const [ackText, setAckText] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!isEditing || initialized || !existingAutomation) return;
    const config = existingAutomation.config as unknown as InstagramHandoffAutomationConfig;
    setKeywordsInput(config.trigger_keywords.join(", "));
    setMatchingMethod(config.matching_method);
    setAckText(config.ack_text);
    setInitialized(true);
  }, [isEditing, initialized, existingAutomation]);

  const keywords = useMemo(() => parseKeywords(keywordsInput), [keywordsInput]);

  const activeMutation = isEditing ? updateMutation : createMutation;
  const mutationError = activeMutation.error as AxiosError<{ detail?: string }> | null;

  function handleNext() {
    if (keywords.length === 0) {
      setValidationError("Add at least one trigger keyword.");
      return;
    }
    setValidationError(null);
    setCurrentStepIndex(1);
  }

  function handleBack() {
    setValidationError(null);
    setCurrentStepIndex(0);
  }

  function handleSubmit() {
    const trimmedAck = ackText.trim();
    if (!trimmedAck) {
      setValidationError("Enter the acknowledgement text to send back.");
      return;
    }
    setValidationError(null);

    const config: InstagramHandoffAutomationConfig = {
      trigger_keywords: keywords,
      matching_method: matchingMethod,
      ack_text: trimmedAck,
    };

    // The shared `InstagramAutomationConfig` union (`../types.ts`) only
    // covers the comment/DM automation shapes - this handoff automation's
    // config is a third, locally-defined shape that isn't part of that
    // union (see this file's module-level types), hence the cast rather
    // than a structural match.
    const configForApi = config as unknown as InstagramAutomationConfig;

    if (isEditing && id) {
      updateMutation.mutate(
        { id, config: configForApi },
        { onSuccess: () => navigate("/communication/instagram/automations") },
      );
      return;
    }

    if (!instagramInstance) return;
    createMutation.mutate(
      {
        connector_instance_id: instagramInstance.id,
        automation_type: INSTAGRAM_HANDOFF_AUTOMATION_TYPE,
        name: keywords.join(", "),
        config: configForApi,
      },
      { onSuccess: () => navigate("/communication/instagram/automations") },
    );
  }

  if (instancesLoading || (isEditing && automationsLoading)) {
    return <p className="text-sm text-muted-foreground">Loading…</p>;
  }

  if (!instagramInstance) {
    return (
      <Card className="mx-auto max-w-lg">
        <CardHeader className="items-center text-center">
          <CardTitle>Connect Instagram first</CardTitle>
          <CardDescription>
            You need a connected Instagram account before you can set up a human handoff automation.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center pb-6">
          <Button onClick={() => navigate("/connectors/instagram/connect")}>Connect Instagram</Button>
        </CardContent>
      </Card>
    );
  }

  const sidebar = (
    <>
      <SummarySidebar
        rows={[
          { label: "Keywords", value: keywords.join(", ") },
          { label: "Matching Method", value: MATCHING_METHOD_LABELS[matchingMethod] },
          { label: "Acknowledgement", value: ackText.trim() || "—" },
        ]}
      />
      <TipsCallout
        tips={[
          "When this fires, the conversation is paused for all other automations until an agent resumes it from the Inbox.",
          "Use keywords a customer would actually type when they want a person, e.g. \"talk to a human\" or \"agent\".",
        ]}
      />
    </>
  );

  const footer = (
    <>
      <Button variant="outline" onClick={() => navigate("/communication/instagram/automations")}>
        Cancel
      </Button>
      {currentStepIndex === 1 && (
        <Button variant="outline" onClick={handleBack}>
          Back
        </Button>
      )}
      {currentStepIndex === 0 ? (
        <Button onClick={handleNext}>Next</Button>
      ) : (
        <Button onClick={handleSubmit} disabled={activeMutation.isPending}>
          {activeMutation.isPending ? "Saving…" : isEditing ? "Save Changes" : "Create Automation"}
        </Button>
      )}
    </>
  );

  return (
    <WizardShell
      title={isEditing ? "Edit Human Handoff" : "New Human Handoff"}
      description="Acknowledge and pause automated replies when a customer asks for a human."
      backTo="/communication/instagram/automations"
      backLabel="Back to automations"
      steps={STEPS}
      currentStepIndex={currentStepIndex}
      sidebar={sidebar}
      footer={footer}
    >
      {currentStepIndex === 0 ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="trigger_keywords" className="text-sm font-medium">
              Trigger keywords
            </label>
            <Input
              id="trigger_keywords"
              placeholder="e.g. talk to a human, agent, help me"
              value={keywordsInput}
              onChange={(event) => setKeywordsInput(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">Separate multiple keywords with commas.</p>
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">Matching method</span>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {MATCHING_METHODS.map((method) => (
                <OptionPickerCard
                  key={method}
                  title={MATCHING_METHOD_LABELS[method]}
                  description={MATCHING_METHOD_DESCRIPTIONS[method]}
                  selected={matchingMethod === method}
                  onSelect={() => setMatchingMethod(method)}
                />
              ))}
            </div>
          </div>

          {validationError && <p className="text-sm text-destructive">{validationError}</p>}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="ack_text" className="text-sm font-medium">
              Acknowledgement message
            </label>
            <Textarea
              id="ack_text"
              rows={4}
              placeholder="e.g. Connecting you to our team — someone will be with you shortly."
              value={ackText}
              onChange={(event) => setAckText(event.target.value)}
            />
          </div>

          {mutationError && (
            <p className="text-sm text-destructive">
              {mutationError.response?.data?.detail ?? "Could not save this automation."}
            </p>
          )}
          {validationError && <p className="text-sm text-destructive">{validationError}</p>}
        </div>
      )}
    </WizardShell>
  );
}
