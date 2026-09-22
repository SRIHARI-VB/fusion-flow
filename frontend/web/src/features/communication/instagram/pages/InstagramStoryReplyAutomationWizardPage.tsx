import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AxiosError } from "axios";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Textarea, cn } from "@fusion-flow/ui";
import { MediaPicker, OptionPickerCard, SummarySidebar, TipsCallout, WizardShell, type SelectedMedia } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import { MATCHING_METHOD_DESCRIPTIONS, MATCHING_METHOD_LABELS, MATCHING_METHODS } from "../constants";
import type { InstagramMatchingMethod, InstagramStoryReplyAutomationConfig } from "../types";

/** Backend automation type key for `POST /api/v1/predefined-automations` -
 * kept local to this file rather than the shared `constants.ts` (per this
 * automation type's own wiring plan). */
const INSTAGRAM_STORY_REPLY_AUTOMATION_TYPE = "instagram.story_reply_automation";

/** "Every reply" (empty `trigger_keywords`, the backend's wildcard) vs.
 * "Specific keywords" (the pre-existing comma-separated keyword input) -
 * purely a wizard-side UI concept, not sent to the backend directly. */
type TriggerMode = "every" | "specific";

/** Up to 6 small emoji buttons for the optional Auto-React toggle - `null`
 * means "no reaction", tapping the selected one again deselects it. */
const REACTION_OPTIONS: Array<{ value: string; emoji: string; label: string }> = [
  { value: "love", emoji: "❤️", label: "Love" },
  { value: "like", emoji: "👍", label: "Like" },
  { value: "laugh", emoji: "😂", label: "Laugh" },
  { value: "wow", emoji: "😮", label: "Wow" },
  { value: "sad", emoji: "😢", label: "Sad" },
  { value: "angry", emoji: "😡", label: "Angry" },
];

const STEPS = ["Keywords & Matching", "Reply"];

/** Same "comma-separated field, trim/dedupe/drop-empties" UX as the
 * comment/DM automation wizards - see `InstagramDmAutomationWizardPage.tsx`. */
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
 * `/communication/instagram/story-reply-automations/new` and
 * `/communication/instagram/story-reply-automations/:id/edit` - the "Story
 * Reply Auto-Reply" wizard: automatically reply via DM when someone replies
 * to a Story posted by this account and their reply text matches a
 * keyword. Sibling to `InstagramDmAutomationWizardPage.tsx`, same shape,
 * different trigger.
 */
export function InstagramStoryReplyAutomationWizardPage() {
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
    foundAutomation && foundAutomation.automation_type === INSTAGRAM_STORY_REPLY_AUTOMATION_TYPE
      ? foundAutomation
      : undefined;

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [triggerMode, setTriggerMode] = useState<TriggerMode>("specific");
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<InstagramMatchingMethod>("contains");
  const [replyText, setReplyText] = useState("");
  const [selectedMedia, setSelectedMedia] = useState<SelectedMedia | null>(null);
  const [replyDelayMinutes, setReplyDelayMinutes] = useState("");
  const [reactEmoji, setReactEmoji] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!isEditing || initialized || !existingAutomation) return;
    const config = existingAutomation.config as InstagramStoryReplyAutomationConfig;
    setTriggerMode(config.trigger_keywords.length === 0 ? "every" : "specific");
    setKeywordsInput(config.trigger_keywords.join(", "));
    setMatchingMethod(config.matching_method);
    setReplyText(config.reply_text);
    setSelectedMedia(config.media_url ? { url: config.media_url, content_type: config.media_type === "video" ? "video" : "image" } : null);
    setReplyDelayMinutes(config.reply_delay_minutes != null ? String(config.reply_delay_minutes) : "");
    setReactEmoji(config.react_emoji ?? null);
    setInitialized(true);
  }, [isEditing, initialized, existingAutomation]);

  const keywords = useMemo(() => parseKeywords(keywordsInput), [keywordsInput]);

  const activeMutation = isEditing ? updateMutation : createMutation;
  const mutationError = activeMutation.error as AxiosError<{ detail?: string }> | null;

  function handleNext() {
    if (triggerMode === "specific" && keywords.length === 0) {
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
      setValidationError("Enter the reply text to send back.");
      return;
    }
    const trimmedDelay = replyDelayMinutes.trim();
    let delayMinutes: number | null = null;
    if (trimmedDelay) {
      const parsedDelay = Number(trimmedDelay);
      if (!Number.isInteger(parsedDelay) || parsedDelay < 1 || parsedDelay > 1440) {
        setValidationError("Reply delay must be a whole number of minutes between 1 and 1440.");
        return;
      }
      delayMinutes = parsedDelay;
    }
    setValidationError(null);

    const config: InstagramStoryReplyAutomationConfig = {
      trigger_keywords: triggerMode === "every" ? [] : keywords,
      matching_method: matchingMethod,
      reply_text: trimmedReply,
      media_url: selectedMedia?.url ?? null,
      media_type: selectedMedia ? (selectedMedia.content_type.startsWith("video") ? "video" : "image") : null,
      react_emoji: reactEmoji,
      reply_delay_minutes: delayMinutes,
    };

    if (isEditing && id) {
      updateMutation.mutate({ id, config }, { onSuccess: () => navigate("/communication/instagram/automations") });
      return;
    }

    if (!instagramInstance) return;
    createMutation.mutate(
      {
        connector_instance_id: instagramInstance.id,
        automation_type: INSTAGRAM_STORY_REPLY_AUTOMATION_TYPE,
        name: triggerMode === "every" ? "Every story reply" : keywords.join(", "),
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
            You need a connected Instagram account before you can set up a Story reply auto-reply.
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
          { label: "Trigger", value: triggerMode === "every" ? "Every story reply" : keywords.join(", ") || "—" },
          ...(triggerMode === "specific"
            ? [{ label: "Matching Method", value: MATCHING_METHOD_LABELS[matchingMethod] }]
            : []),
          { label: "Reply", value: replyText.trim() || "—" },
          { label: "Media", value: selectedMedia ? "Attached" : "—" },
          { label: "Reply Delay", value: replyDelayMinutes ? `${replyDelayMinutes} min` : "None" },
          { label: "Auto-React", value: reactEmoji ? REACTION_OPTIONS.find((option) => option.value === reactEmoji)?.label ?? reactEmoji : "None" },
        ]}
      />
      <TipsCallout
        tips={[
          "This automation checks every reply to any Story this account posts.",
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
      title={isEditing ? "Edit Story Reply Auto-Reply" : "New Story Reply Auto-Reply"}
      description="Automatically reply via DM when someone replies to one of your Stories and their message matches a keyword."
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
            <span className="text-sm font-medium">Which replies should trigger this?</span>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <OptionPickerCard
                title="Every reply"
                description="Trigger on any reply to any Story this account posts, regardless of what it says."
                selected={triggerMode === "every"}
                onSelect={() => setTriggerMode("every")}
              />
              <OptionPickerCard
                title="Specific keywords"
                description="Only trigger when the reply text matches one of your configured keywords."
                selected={triggerMode === "specific"}
                onSelect={() => setTriggerMode("specific")}
              />
            </div>
          </div>

          {triggerMode === "specific" && (
            <>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="trigger_keywords" className="text-sm font-medium">
                  Trigger keywords
                </label>
                <Input
                  id="trigger_keywords"
                  placeholder="e.g. discount, code, giveaway"
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
              placeholder="e.g. Thanks for replying! Here's the info you asked for..."
              value={replyText}
              onChange={(event) => setReplyText(event.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Attach media (optional)</span>
            <p className="text-xs text-muted-foreground">
              Send an image or video alongside the reply text above.
            </p>
            <MediaPicker value={selectedMedia} onChange={setSelectedMedia} />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="reply_delay_minutes" className="text-sm font-medium">
              Reply delay (optional)
            </label>
            <Input
              id="reply_delay_minutes"
              type="number"
              min={1}
              max={1440}
              placeholder="e.g. 2"
              value={replyDelayMinutes}
              onChange={(event) => setReplyDelayMinutes(event.target.value)}
              className="max-w-[160px]"
            />
            <p className="text-xs text-muted-foreground">
              Minutes to wait before sending the reply. Leave blank to reply immediately.
            </p>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Auto-react to the reply (optional)</span>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setReactEmoji(null)}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-xs font-medium transition-colors",
                  reactEmoji === null ? "border-accent bg-accent-soft text-accent" : "border-border hover:bg-muted",
                )}
              >
                None
              </button>
              {REACTION_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  title={option.label}
                  onClick={() => setReactEmoji((current) => (current === option.value ? null : option.value))}
                  className={cn(
                    "flex h-9 w-9 items-center justify-center rounded-md border text-lg transition-colors",
                    reactEmoji === option.value ? "border-accent bg-accent-soft" : "border-border hover:bg-muted",
                  )}
                >
                  {option.emoji}
                </button>
              ))}
            </div>
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
