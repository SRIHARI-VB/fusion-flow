import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AxiosError } from "axios";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Textarea } from "@fusion-flow/ui";
import { OptionPickerCard, SummarySidebar, TipsCallout, WizardShell } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import type { InstagramAutomationConfig } from "../types";

const INSTAGRAM_REACTION_AUTOMATION_TYPE = "instagram.reaction_automation";

type InstagramReactionType = "love" | "like" | "laugh" | "wow" | "sad" | "angry";

/** `config` for `automation_type: "instagram.reaction_automation"` - kept
 * local to this file rather than added to the shared `types.ts` union. */
interface InstagramReactionAutomationConfig {
  reaction_type: InstagramReactionType;
  reply_text: string;
}

const REACTION_OPTIONS: { value: InstagramReactionType; title: string; description: string }[] = [
  { value: "love", title: "Love ❤️", description: "Reacted with a heart." },
  { value: "like", title: "Like 👍", description: "Reacted with a thumbs up." },
  { value: "laugh", title: "Laugh 😂", description: "Reacted with a laughing face." },
  { value: "wow", title: "Wow 😮", description: "Reacted with a surprised face." },
  { value: "sad", title: "Sad 😢", description: "Reacted with a sad face." },
  { value: "angry", title: "Angry 😡", description: "Reacted with an angry face." },
];

const REACTION_LABELS: Record<InstagramReactionType, string> = {
  love: "Love ❤️",
  like: "Like 👍",
  laugh: "Laugh 😂",
  wow: "Wow 😮",
  sad: "Sad 😢",
  angry: "Angry 😡",
};

const STEPS = ["Reaction Type", "Reply"];

/**
 * `/communication/instagram/reaction-automations/new` and
 * `/communication/instagram/reaction-automations/:id/edit` - the "Reaction
 * Follow-Up" wizard: automatically send a DM follow-up when someone reacts
 * to a message in a DM conversation with this account with a specific
 * reaction type. Sibling to `InstagramDmAutomationWizardPage.tsx`, simpler
 * still - no free-text keyword input or matching-method picker, just a
 * fixed set of reaction-type options.
 */
export function InstagramReactionAutomationWizardPage() {
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
    foundAutomation && foundAutomation.automation_type === INSTAGRAM_REACTION_AUTOMATION_TYPE
      ? foundAutomation
      : undefined;

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [reactionType, setReactionType] = useState<InstagramReactionType>("love");
  const [replyText, setReplyText] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!isEditing || initialized || !existingAutomation) return;
    const config = existingAutomation.config as unknown as InstagramReactionAutomationConfig;
    setReactionType(config.reaction_type);
    setReplyText(config.reply_text);
    setInitialized(true);
  }, [isEditing, initialized, existingAutomation]);

  const activeMutation = isEditing ? updateMutation : createMutation;
  const mutationError = activeMutation.error as AxiosError<{ detail?: string }> | null;

  function handleNext() {
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
      setValidationError("Enter the reply text to send back.");
      return;
    }
    setValidationError(null);

    const config: InstagramReactionAutomationConfig = {
      reaction_type: reactionType,
      reply_text: trimmedReply,
    };
    const payloadConfig = config as unknown as InstagramAutomationConfig;

    if (isEditing && id) {
      updateMutation.mutate(
        { id, config: payloadConfig },
        { onSuccess: () => navigate("/communication/instagram/automations") },
      );
      return;
    }

    if (!instagramInstance) return;
    createMutation.mutate(
      {
        connector_instance_id: instagramInstance.id,
        automation_type: INSTAGRAM_REACTION_AUTOMATION_TYPE,
        name: `${REACTION_LABELS[reactionType]} Follow-Up`,
        config: payloadConfig,
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
            You need a connected Instagram account before you can set up a reaction follow-up.
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
          { label: "Reaction Type", value: REACTION_LABELS[reactionType] },
          { label: "Reply", value: replyText.trim() || "—" },
        ]}
      />
      <TipsCallout
        tips={[
          "This automation checks reactions to messages in this account's DM conversations.",
          "Keep the reply short - it sends as a normal DM, not a template.",
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
      title={isEditing ? "Edit Reaction Follow-Up" : "New Reaction Follow-Up"}
      description="Automatically send a DM follow-up when someone reacts to a message with a specific reaction."
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
            <span className="text-sm font-medium">Reaction type</span>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {REACTION_OPTIONS.map((option) => (
                <OptionPickerCard
                  key={option.value}
                  title={option.title}
                  description={option.description}
                  selected={reactionType === option.value}
                  onSelect={() => setReactionType(option.value)}
                />
              ))}
            </div>
          </div>

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
              placeholder="e.g. Thanks for the love! Here's a little something extra..."
              value={replyText}
              onChange={(event) => setReplyText(event.target.value)}
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
