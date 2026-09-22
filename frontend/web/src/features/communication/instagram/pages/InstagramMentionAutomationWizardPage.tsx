import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AxiosError } from "axios";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Textarea } from "@fusion-flow/ui";
import { OptionPickerCard, SummarySidebar, TipsCallout, WizardShell } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import { MATCHING_METHOD_DESCRIPTIONS, MATCHING_METHOD_LABELS, MATCHING_METHODS } from "../constants";
import type { InstagramMatchingMethod } from "../types";

const INSTAGRAM_MENTION_AUTOMATION_TYPE = "instagram.mention_automation";

/** `config` for `automation_type: "instagram.mention_automation"` - kept
 * local to this file rather than added to the shared `types.ts` union. */
interface InstagramMentionAutomationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  reply_text: string;
  reply_delay_minutes: number | null;
}

/** "Every mention" sends `trigger_keywords: []` (the backend's
 * `build_keyword_condition_chain` treats an empty list as "match
 * everything" - no condition nodes at all), hiding the keyword input and
 * matching-method picker since neither applies. */
type TriggerScope = "every" | "specific";

const STEPS = ["Keywords & Matching", "Reply"];

/** Same "comma-separated field, trim/dedupe/drop-empties" UX as the
 * DM automation wizard - see `InstagramDmAutomationWizardPage.tsx`. */
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
 * `/communication/instagram/mention-automations/new` and
 * `/communication/instagram/mention-automations/:id/edit` - the "Mention
 * Auto-Reply" wizard: automatically reply to a comment where someone
 * mentions this account, when the comment text matches a keyword. Sibling
 * to `InstagramDmAutomationWizardPage.tsx`, same two-step shape.
 */
export function InstagramMentionAutomationWizardPage() {
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
    foundAutomation && foundAutomation.automation_type === INSTAGRAM_MENTION_AUTOMATION_TYPE
      ? foundAutomation
      : undefined;

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [triggerScope, setTriggerScope] = useState<TriggerScope>("specific");
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<InstagramMatchingMethod>("contains");
  const [replyText, setReplyText] = useState("");
  const [replyDelayMinutesInput, setReplyDelayMinutesInput] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!isEditing || initialized || !existingAutomation) return;
    const config = existingAutomation.config as InstagramMentionAutomationConfig;
    setTriggerScope(config.trigger_keywords.length === 0 ? "every" : "specific");
    setKeywordsInput(config.trigger_keywords.join(", "));
    setMatchingMethod(config.matching_method);
    setReplyText(config.reply_text);
    setReplyDelayMinutesInput(
      config.reply_delay_minutes === null || config.reply_delay_minutes === undefined
        ? ""
        : String(config.reply_delay_minutes),
    );
    setInitialized(true);
  }, [isEditing, initialized, existingAutomation]);

  const keywords = useMemo(() => parseKeywords(keywordsInput), [keywordsInput]);

  const activeMutation = isEditing ? updateMutation : createMutation;
  const mutationError = activeMutation.error as AxiosError<{ detail?: string }> | null;

  function handleNext() {
    if (triggerScope === "specific" && keywords.length === 0) {
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
    const trimmedReply = replyText.trim();
    if (!trimmedReply) {
      setValidationError("Enter the reply text to post back on the comment.");
      return;
    }
    const trimmedDelay = replyDelayMinutesInput.trim();
    let replyDelayMinutes: number | null = null;
    if (trimmedDelay) {
      const parsedDelay = Number(trimmedDelay);
      if (!Number.isInteger(parsedDelay) || parsedDelay < 1 || parsedDelay > 1440) {
        setValidationError("Reply delay must be a whole number of minutes between 1 and 1440.");
        return;
      }
      replyDelayMinutes = parsedDelay;
    }
    setValidationError(null);

    const config: InstagramMentionAutomationConfig = {
      trigger_keywords: triggerScope === "every" ? [] : keywords,
      matching_method: matchingMethod,
      reply_text: trimmedReply,
      reply_delay_minutes: replyDelayMinutes,
    };

    if (isEditing && id) {
      updateMutation.mutate({ id, config }, { onSuccess: () => navigate("/communication/instagram/automations") });
      return;
    }

    if (!instagramInstance) return;
    createMutation.mutate(
      {
        connector_instance_id: instagramInstance.id,
        automation_type: INSTAGRAM_MENTION_AUTOMATION_TYPE,
        name: triggerScope === "every" ? "Every mention" : keywords.join(", "),
        config,
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
            You need a connected Instagram account before you can set up a mention auto-reply.
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
          {
            label: "Trigger",
            value: triggerScope === "every" ? "Every mention" : keywords.join(", ") || "—",
          },
          ...(triggerScope === "specific"
            ? [{ label: "Matching Method", value: MATCHING_METHOD_LABELS[matchingMethod] }]
            : []),
          { label: "Reply", value: replyText.trim() || "—" },
          {
            label: "Reply Delay",
            value: replyDelayMinutesInput.trim() ? `${replyDelayMinutesInput.trim()} min` : "None",
          },
        ]}
      />
      <TipsCallout
        tips={[
          "This only works when someone @mentions this account in a comment on their own post.",
          "A caption mention (tagged in the post description, not a comment) has no comment to reply to, so it's skipped.",
          "Keep the reply short - it posts as a normal comment reply.",
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
      title={isEditing ? "Edit Mention Auto-Reply" : "New Mention Auto-Reply"}
      description="Automatically reply when someone mentions this account in a comment and it matches keywords you choose."
      backTo="/communication/instagram/automations"
      backLabel="Back to automations"
      steps={STEPS}
      currentStepIndex={currentStepIndex}
      sidebar={sidebar}
      footer={footer}
    >
      {currentStepIndex === 0 ? (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">Which mentions?</span>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <OptionPickerCard
                title="Every mention"
                description="Reply to any comment that mentions this account, no keyword filtering."
                selected={triggerScope === "every"}
                onSelect={() => setTriggerScope("every")}
              />
              <OptionPickerCard
                title="Specific keywords"
                description="Only reply when the mentioning comment also matches a keyword."
                selected={triggerScope === "specific"}
                onSelect={() => setTriggerScope("specific")}
              />
            </div>
          </div>

          {triggerScope === "specific" && (
            <>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="trigger_keywords" className="text-sm font-medium">
                  Trigger keywords
                </label>
                <Input
                  id="trigger_keywords"
                  placeholder="e.g. thanks, love this, amazing"
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
            </>
          )}

          {validationError && <p className="text-sm text-destructive">{validationError}</p>}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label htmlFor="reply_text" className="text-sm font-medium">
              Reply message
            </label>
            <Textarea
              id="reply_text"
              rows={4}
              placeholder="e.g. Thanks so much for the shoutout!"
              value={replyText}
              onChange={(event) => setReplyText(event.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="reply_delay_minutes" className="text-sm font-medium">
              Reply delay (minutes)
            </label>
            <Input
              id="reply_delay_minutes"
              type="number"
              min={1}
              max={1440}
              placeholder="Reply immediately"
              value={replyDelayMinutesInput}
              onChange={(event) => setReplyDelayMinutesInput(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Optional. Wait this many minutes before posting the reply, so it doesn't look instantly automated.
              Leave blank to reply immediately.
            </p>
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
