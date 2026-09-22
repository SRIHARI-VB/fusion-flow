import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { EyeOff } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, cn } from "@fusion-flow/ui";
import { OptionPickerCard, SummarySidebar, TipsCallout, ToggleSettingRow, WizardShell } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import {
  INSTAGRAM_COMMENT_AUTOMATION_TYPE,
  MATCHING_METHOD_DESCRIPTIONS,
  MATCHING_METHOD_LABELS,
  MATCHING_METHODS,
} from "../constants";
import { isCommentAutomationConfig, type InstagramCommentAutomationConfig, type InstagramMatchingMethod } from "../types";
import { fetchInstagramMedia } from "../media-api";

const STEPS = ["Keywords & Matching", "Actions"];

/** `types.ts` is shared/off-limits for this feature slice, so the two
 * newest config fields (both backend-supported already) are layered on
 * locally rather than added there - same shape the backend's
 * `InstagramCommentAutomationConfig` (Python) now accepts. Optional so a
 * `PredefinedAutomation` fetched before this feature shipped (missing
 * both keys entirely) still narrows cleanly. */
type CommentAutomationConfig = InstagramCommentAutomationConfig & {
  reply_delay_minutes?: number | null;
  media_id?: string | null;
};

/** Match choice shown at the top of Step 1 - "All comments" collapses
 * `trigger_keywords` to `[]` (the backend's wildcard, see
 * `graph_helpers.build_keyword_condition_chain`), so the keyword input
 * (and the matching-method picker, meaningless without a keyword) is
 * hidden entirely while this is selected. */
type MatchMode = "all" | "keywords";

/** Splits the free-text keyword field into `trigger_keywords`, trimming
 * whitespace and dropping empties/duplicates - the "simple comma-separated
 * field" UX the spec calls for in place of a full tag-input widget. */
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
 * `/communication/instagram/automations/new` and
 * `/communication/instagram/automations/:id/edit` - the "Comment
 * Automation" wizard. Account-wide by default (fires on comments across
 * every post/reel on the connected Instagram account) unless a specific
 * post/reel is picked in the "Scope" section, which scopes the generated
 * graph to just that one (`media_id`, see the backend's `build_graph`).
 */
export function InstagramAutomationWizardPage() {
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
    foundAutomation && isCommentAutomationConfig(foundAutomation) ? foundAutomation : undefined;

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [matchMode, setMatchMode] = useState<MatchMode>("keywords");
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<InstagramMatchingMethod>("contains");
  const [mediaId, setMediaId] = useState<string | null>(null);
  const [autoHide, setAutoHide] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [dmText, setDmText] = useState("");
  const [replyDelayMinutesInput, setReplyDelayMinutesInput] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  // This account's own posts/reels - the "Scope" grid's options. Fetched
  // once `instagramInstance` is resolved; not gated on `matchMode`/step
  // since editing an existing scoped automation needs it available
  // immediately to render the current selection.
  const { data: mediaItems, isLoading: mediaLoading } = useQuery({
    queryKey: ["instagram-media", instagramInstance?.id],
    queryFn: () => fetchInstagramMedia(instagramInstance!.id),
    enabled: Boolean(instagramInstance),
  });

  // Seeds form state from the fetched automation exactly once, when
  // editing - guarded by `initialized` so a background refetch (e.g. the
  // list's polling) never clobbers what the tenant is mid-typing.
  useEffect(() => {
    if (!isEditing || initialized || !existingAutomation) return;
    const config = existingAutomation.config as CommentAutomationConfig;
    setMatchMode(config.trigger_keywords.length === 0 ? "all" : "keywords");
    setKeywordsInput(config.trigger_keywords.join(", "));
    setMatchingMethod(config.matching_method);
    setMediaId(config.media_id ?? null);
    setAutoHide(config.auto_hide);
    setReplyText(config.reply_comment_text ?? "");
    setDmText(config.dm_text ?? "");
    setReplyDelayMinutesInput(config.reply_delay_minutes ? String(config.reply_delay_minutes) : "");
    setInitialized(true);
  }, [isEditing, initialized, existingAutomation]);

  const keywords = useMemo(() => parseKeywords(keywordsInput), [keywordsInput]);

  const activeMutation = isEditing ? updateMutation : createMutation;
  const mutationError = activeMutation.error as AxiosError<{ detail?: string }> | null;

  function handleNext() {
    if (matchMode === "keywords" && keywords.length === 0) {
      setValidationError("Add at least one trigger keyword, or switch to \"All comments\".");
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
    const trimmedDm = dmText.trim();
    if (!autoHide && !trimmedReply && !trimmedDm) {
      setValidationError(
        "Turn on at least one action - Auto-Hide, a public reply, or a DM reply - before saving.",
      );
      return;
    }
    setValidationError(null);

    const parsedDelay = Number(replyDelayMinutesInput);
    const reply_delay_minutes =
      replyDelayMinutesInput.trim() === "" || !Number.isFinite(parsedDelay) || parsedDelay <= 0
        ? null
        : Math.min(1440, Math.round(parsedDelay));

    const config: CommentAutomationConfig = {
      trigger_keywords: matchMode === "all" ? [] : keywords,
      matching_method: matchingMethod,
      auto_hide: autoHide,
      reply_comment_text: trimmedReply || null,
      dm_text: trimmedDm || null,
      reply_delay_minutes,
      media_id: mediaId,
    };

    if (isEditing && id) {
      updateMutation.mutate({ id, config }, { onSuccess: () => navigate("/communication/instagram/automations") });
      return;
    }

    if (!instagramInstance) return;
    createMutation.mutate(
      {
        connector_instance_id: instagramInstance.id,
        automation_type: INSTAGRAM_COMMENT_AUTOMATION_TYPE,
        name: matchMode === "all" ? "All comments" : keywords.join(", "),
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
            You need a connected Instagram account before you can set up a comment automation.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex justify-center pb-6">
          <Button onClick={() => navigate("/connectors/instagram/connect")}>Connect Instagram</Button>
        </CardContent>
      </Card>
    );
  }

  const selectedMedia = mediaId ? (mediaItems ?? []).find((item) => item.id === mediaId) : undefined;

  const sidebar = (
    <>
      <SummarySidebar
        rows={[
          { label: "Matches", value: matchMode === "all" ? "All comments" : keywords.join(", ") || "—" },
          ...(matchMode === "keywords"
            ? [{ label: "Matching Method", value: MATCHING_METHOD_LABELS[matchingMethod] }]
            : []),
          { label: "Scope", value: mediaId ? selectedMedia?.caption?.slice(0, 24) || mediaId : "All posts/reels" },
          { label: "Reply Delay", value: replyDelayMinutesInput.trim() ? `${replyDelayMinutesInput} min` : "None" },
          { label: "Auto-Hide", value: autoHide ? "On" : "Off" },
          { label: "Public Reply", value: replyText.trim() || "Off" },
          { label: "DM Reply", value: dmText.trim() || "Off" },
        ]}
      />
      <TipsCallout
        tips={[
          "By default this automation checks every comment on every post/reel on this account - scope it to one post/reel in the Scope section.",
          "A reply delay makes automated replies feel a little less instant.",
          "Auto-Hide keeps your posts clean from bot replies or competitor scraping.",
          "You can enable both a public reply and a DM reply at the same time.",
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
      title={isEditing ? "Edit Comment Automation" : "New Comment Automation"}
      description="Automatically hide or reply to Instagram comments that match keywords you choose."
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
            <span className="text-sm font-medium">Which comments should this match?</span>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <OptionPickerCard
                title="All comments"
                description="Match every comment, regardless of what it says."
                selected={matchMode === "all"}
                onSelect={() => setMatchMode("all")}
              />
              <OptionPickerCard
                title="Specific keywords"
                description="Only match comments containing certain words."
                selected={matchMode === "keywords"}
                onSelect={() => setMatchMode("keywords")}
              />
            </div>
          </div>

          {matchMode === "keywords" && (
            <>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="trigger_keywords" className="text-sm font-medium">
                  Trigger keywords
                </label>
                <Input
                  id="trigger_keywords"
                  placeholder="e.g. price, info, discount"
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

          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">Scope</span>
            <p className="text-xs text-muted-foreground">
              Apply this automation to every post/reel, or just one.
            </p>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              <button
                type="button"
                onClick={() => setMediaId(null)}
                className={cn(
                  "flex h-28 flex-col items-center justify-center gap-1 rounded-md border p-2 text-center transition-colors",
                  mediaId === null ? "border-accent bg-accent-soft" : "border-border hover:bg-muted",
                )}
              >
                <span className={cn("text-sm font-medium", mediaId === null ? "text-accent" : "text-foreground")}>
                  All posts/reels
                </span>
                <span className="text-xs text-muted-foreground">Account-wide</span>
              </button>

              {mediaLoading && (
                <p className="col-span-full text-xs text-muted-foreground">Loading your posts…</p>
              )}

              {(mediaItems ?? []).map((media) => {
                const thumbnail = media.thumbnail_url || media.media_url;
                const selected = mediaId === media.id;
                return (
                  <button
                    key={media.id}
                    type="button"
                    onClick={() => setMediaId(media.id)}
                    className={cn(
                      "flex h-28 flex-col overflow-hidden rounded-md border text-left transition-colors",
                      selected ? "border-accent" : "border-border hover:bg-muted",
                    )}
                  >
                    {thumbnail ? (
                      <img src={thumbnail} alt="" className="h-20 w-full object-cover" />
                    ) : (
                      <div className="flex h-20 w-full items-center justify-center bg-muted text-xs text-muted-foreground">
                        {media.media_type}
                      </div>
                    )}
                    <span className="flex-1 truncate p-1 text-[11px] text-muted-foreground">
                      {media.caption?.slice(0, 40) || media.media_type}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {validationError && <p className="text-sm text-destructive">{validationError}</p>}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <ToggleSettingRow
            icon={EyeOff}
            label="Auto-Hide"
            description="Hides the comment to prevent spam or copycats"
            checked={autoHide}
            onCheckedChange={setAutoHide}
          />

          <div className="flex flex-col gap-1.5">
            <label htmlFor="reply_comment_text" className="text-sm font-medium">
              Public reply <span className="text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="reply_comment_text"
              placeholder="e.g. Check your DM for details!"
              value={replyText}
              onChange={(event) => setReplyText(event.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="dm_text" className="text-sm font-medium">
              DM reply <span className="text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="dm_text"
              placeholder="e.g. Thanks! Here's the info you asked for..."
              value={dmText}
              onChange={(event) => setDmText(event.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="reply_delay_minutes" className="text-sm font-medium">
              Reply Delay (minutes) <span className="text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="reply_delay_minutes"
              type="number"
              min={0}
              max={1440}
              placeholder="e.g. 5"
              value={replyDelayMinutesInput}
              onChange={(event) => setReplyDelayMinutesInput(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Wait this long before acting on a match. Leave empty (or 0) to act immediately.
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
