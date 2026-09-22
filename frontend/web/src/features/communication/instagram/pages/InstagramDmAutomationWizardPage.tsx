import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AxiosError } from "axios";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Textarea, cn } from "@fusion-flow/ui";
import { MediaPicker, OptionPickerCard, SummarySidebar, TipsCallout, WizardShell, type SelectedMedia } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import {
  INSTAGRAM_DM_AUTOMATION_TYPE,
  MATCHING_METHOD_DESCRIPTIONS,
  MATCHING_METHOD_LABELS,
  MATCHING_METHODS,
} from "../constants";
import type { InstagramDmAutomationConfig, InstagramMatchingMethod } from "../types";

const STEPS = ["Keywords & Matching", "Reply"];

/** Local-only reaction-emoji picker options - one of these six or none.
 * Kept in this file (not `constants.ts`) since only this wizard exposes it
 * so far. */
const REACTION_OPTIONS: Array<{ emoji: string; value: ReactionEmoji; label: string }> = [
  { emoji: "❤️", value: "love", label: "Love" },
  { emoji: "👍", value: "like", label: "Like" },
  { emoji: "😂", value: "laugh", label: "Laugh" },
  { emoji: "😮", value: "wow", label: "Wow" },
  { emoji: "😢", value: "sad", label: "Sad" },
  { emoji: "😡", value: "angry", label: "Angry" },
];

type ReactionEmoji = "love" | "like" | "laugh" | "wow" | "sad" | "angry";

/** Local extension of the shared `InstagramDmAutomationConfig` DTO with the
 * four new optional fields this wizard now supports - kept here rather
 * than in the shared `types.ts` (per this feature's convention of not
 * widening a shared DTO for a single wizard's still-evolving shape). */
interface InstagramDmAutomationConfigExtended extends InstagramDmAutomationConfig {
  react_emoji: ReactionEmoji | null;
  reply_delay_minutes: number | null;
  media_url: string | null;
  media_type: string | null;
}

/** Same "comma-separated field, trim/dedupe/drop-empties" UX as the
 * comment automation wizard - see `InstagramAutomationWizardPage.tsx`. */
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
 * `/communication/instagram/dm-automations/new` and
 * `/communication/instagram/dm-automations/:id/edit` - the "DM Auto-Reply"
 * wizard: automatically reply to an inbound direct message when its text
 * matches a keyword. Sibling to `InstagramAutomationWizardPage.tsx`
 * (comment automation), much smaller since there's only one action.
 */
export function InstagramDmAutomationWizardPage() {
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
    foundAutomation && foundAutomation.automation_type === INSTAGRAM_DM_AUTOMATION_TYPE ? foundAutomation : undefined;

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [matchAll, setMatchAll] = useState(false);
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<InstagramMatchingMethod>("contains");
  const [replyText, setReplyText] = useState("");
  const [media, setMedia] = useState<SelectedMedia | null>(null);
  const [reactEmoji, setReactEmoji] = useState<ReactionEmoji | null>(null);
  const [replyDelayInput, setReplyDelayInput] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!isEditing || initialized || !existingAutomation) return;
    const config = existingAutomation.config as InstagramDmAutomationConfigExtended;
    setMatchAll(config.trigger_keywords.length === 0);
    setKeywordsInput(config.trigger_keywords.join(", "));
    setMatchingMethod(config.matching_method);
    setReplyText(config.reply_text);
    if (config.media_url) {
      setMedia({ url: config.media_url, content_type: config.media_type === "video" ? "video/*" : "image/*" });
    }
    setReactEmoji(config.react_emoji ?? null);
    setReplyDelayInput(config.reply_delay_minutes ? String(config.reply_delay_minutes) : "");
    setInitialized(true);
  }, [isEditing, initialized, existingAutomation]);

  const keywords = useMemo(() => parseKeywords(keywordsInput), [keywordsInput]);

  const activeMutation = isEditing ? updateMutation : createMutation;
  const mutationError = activeMutation.error as AxiosError<{ detail?: string }> | null;

  function handleNext() {
    if (!matchAll && keywords.length === 0) {
      setValidationError("Add at least one trigger keyword, or choose \"All messages\".");
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

    const trimmedDelay = replyDelayInput.trim();
    let replyDelayMinutes: number | null = null;
    if (trimmedDelay) {
      const parsedDelay = Number(trimmedDelay);
      if (!Number.isFinite(parsedDelay) || parsedDelay < 1 || parsedDelay > 1440) {
        setValidationError("Reply delay must be a whole number of minutes between 1 and 1440.");
        return;
      }
      replyDelayMinutes = Math.round(parsedDelay);
    }
    setValidationError(null);

    const config: InstagramDmAutomationConfigExtended = {
      trigger_keywords: matchAll ? [] : keywords,
      matching_method: matchingMethod,
      reply_text: trimmedReply,
      react_emoji: reactEmoji,
      reply_delay_minutes: replyDelayMinutes,
      media_url: media?.url ?? null,
      media_type: media ? (media.content_type.startsWith("video") ? "video" : "image") : null,
    };

    if (isEditing && id) {
      updateMutation.mutate({ id, config }, { onSuccess: () => navigate("/communication/instagram/automations") });
      return;
    }

    if (!instagramInstance) return;
    createMutation.mutate(
      {
        connector_instance_id: instagramInstance.id,
        automation_type: INSTAGRAM_DM_AUTOMATION_TYPE,
        name: matchAll ? "All messages" : keywords.join(", "),
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
            You need a connected Instagram account before you can set up a DM auto-reply.
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
          { label: "Keywords", value: matchAll ? "All messages" : keywords.join(", ") },
          { label: "Matching Method", value: matchAll ? "—" : MATCHING_METHOD_LABELS[matchingMethod] },
          { label: "Reply", value: replyText.trim() || "—" },
          { label: "Media", value: media ? media.url : "—" },
          { label: "Reaction", value: reactEmoji ? REACTION_OPTIONS.find((o) => o.value === reactEmoji)!.label : "—" },
          { label: "Reply Delay", value: replyDelayInput.trim() ? `${replyDelayInput.trim()} min` : "—" },
        ]}
      />
      <TipsCallout
        tips={[
          "This automation checks every direct message this account receives.",
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
      title={isEditing ? "Edit DM Auto-Reply" : "New DM Auto-Reply"}
      description="Automatically reply to Instagram direct messages that match keywords you choose."
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
            <span className="text-sm font-medium">Which messages should trigger this?</span>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <OptionPickerCard
                title="All messages"
                description="Reply to every direct message this account receives, no keyword filtering."
                selected={matchAll}
                onSelect={() => setMatchAll(true)}
              />
              <OptionPickerCard
                title="Specific keywords"
                description="Only reply when the message text matches one of your keywords."
                selected={!matchAll}
                onSelect={() => setMatchAll(false)}
              />
            </div>
          </div>

          {!matchAll && (
            <>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="trigger_keywords" className="text-sm font-medium">
                  Trigger keywords
                </label>
                <Input
                  id="trigger_keywords"
                  placeholder="e.g. price, hours, hi"
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
              placeholder="e.g. Thanks for reaching out! Here's the info you asked for..."
              value={replyText}
              onChange={(event) => setReplyText(event.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">Attach media (optional)</span>
            <MediaPicker value={media} onChange={setMedia} />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="reply_delay_minutes" className="text-sm font-medium">
              Reply delay (minutes, optional)
            </label>
            <Input
              id="reply_delay_minutes"
              type="number"
              min={1}
              max={1440}
              placeholder="Send immediately"
              value={replyDelayInput}
              onChange={(event) => setReplyDelayInput(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">Wait this many minutes before sending the reply (max 1440 = 24h).</p>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-sm font-medium">React to the message (optional)</span>
            <div className="flex flex-wrap gap-2">
              {REACTION_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  title={option.label}
                  onClick={() => setReactEmoji(reactEmoji === option.value ? null : option.value)}
                  className={cn(
                    "flex h-10 w-10 items-center justify-center rounded-md border text-lg transition-colors",
                    reactEmoji === option.value ? "border-accent bg-accent-soft" : "border-border hover:bg-muted",
                  )}
                >
                  {option.emoji}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {reactEmoji ? `Selected: ${REACTION_OPTIONS.find((o) => o.value === reactEmoji)!.label} (tap again to remove)` : "No reaction selected."}
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
