import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { EyeOff, Trash2 } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { OptionPickerCard, SummarySidebar, TipsCallout, ToggleSettingRow, WizardShell } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import { MATCHING_METHOD_DESCRIPTIONS, MATCHING_METHOD_LABELS, MATCHING_METHODS } from "../constants";
import type { InstagramMatchingMethod } from "../types";
import { fetchInstagramMedia } from "../media-api";

/** Backend automation type key for `POST /api/v1/predefined-automations` -
 * kept local to this file (not the shared `constants.ts`) per this
 * automation's scope. */
const INSTAGRAM_COMMENT_MODERATION_TYPE = "instagram.comment_moderation";

/** `config` for `automation_type: "instagram.comment_moderation"` - kept
 * local to this file (not the shared `types.ts`) per this automation's
 * scope. Purely a filtering automation (hide/delete) - no reply/DM fields
 * at all, unlike `InstagramCommentAutomationConfig`. */
interface InstagramCommentModerationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  hide: boolean;
  delete: boolean;
  media_id: string | null;
}

/** "All comments" vs "Specific keywords" - the wizard's own toggle, not a
 * persisted field. `trigger_keywords` is what actually goes over the wire
 * (`[]` for "all"), derived from this at submit time. */
type CommentScope = "all" | "keywords";

const STEPS = ["Keywords & Matching", "Actions"];

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
 * `/communication/instagram/automations/:id/edit` (routed by the
 * coordinator's wiring) - the "Comment Moderation" wizard. Purely a
 * spam/abuse filter (hide and/or delete matching comments) - distinct
 * from `InstagramAutomationWizardPage`'s "Comment Automation", which is
 * about replying to genuine engagement. Account-wide by default (every
 * post/reel), optionally scoped down to a single post/reel via the
 * "Scope" picker on step 1 (`config.media_id`).
 */
export function InstagramCommentModerationWizardPage() {
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
  const foundAutomation = isEditing
    ? automations?.find((automation) => automation.id === id)
    : undefined;
  const existingAutomation =
    foundAutomation && foundAutomation.automation_type === INSTAGRAM_COMMENT_MODERATION_TYPE
      ? (foundAutomation as unknown as { config: InstagramCommentModerationConfig })
      : undefined;

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [commentScope, setCommentScope] = useState<CommentScope>("keywords");
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<InstagramMatchingMethod>("contains");
  const [mediaId, setMediaId] = useState<string | null>(null);
  const [hide, setHide] = useState(false);
  const [deleteComment, setDeleteComment] = useState(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

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
    const config = existingAutomation.config;
    setCommentScope(config.trigger_keywords.length === 0 ? "all" : "keywords");
    setKeywordsInput(config.trigger_keywords.join(", "));
    setMatchingMethod(config.matching_method);
    setMediaId(config.media_id ?? null);
    setHide(config.hide);
    setDeleteComment(config.delete);
    setInitialized(true);
  }, [isEditing, initialized, existingAutomation]);

  const keywords = useMemo(() => parseKeywords(keywordsInput), [keywordsInput]);

  const activeMutation = isEditing ? updateMutation : createMutation;
  const mutationError = activeMutation.error as AxiosError<{ detail?: string }> | null;

  function handleNext() {
    if (commentScope === "keywords" && keywords.length === 0) {
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
    if (!hide && !deleteComment) {
      setValidationError("Turn on at least one action - Hide or Delete - before saving.");
      return;
    }
    setValidationError(null);

    const config: InstagramCommentModerationConfig = {
      trigger_keywords: commentScope === "all" ? [] : keywords,
      matching_method: matchingMethod,
      hide,
      delete: deleteComment,
      media_id: mediaId,
    };

    if (isEditing && id) {
      updateMutation.mutate(
        { id, config: config as unknown as Parameters<typeof updateMutation.mutate>[0]["config"] },
        { onSuccess: () => navigate("/communication/instagram/automations") },
      );
      return;
    }

    if (!instagramInstance) return;
    createMutation.mutate(
      {
        connector_instance_id: instagramInstance.id,
        automation_type: INSTAGRAM_COMMENT_MODERATION_TYPE,
        name: commentScope === "all" ? "All comments" : keywords.join(", "),
        config: config as unknown as Parameters<typeof createMutation.mutate>[0]["config"],
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
            You need a connected Instagram account before you can set up comment moderation.
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
            label: "Keywords",
            value: commentScope === "all" ? "All comments" : keywords.join(", "),
          },
          { label: "Matching Method", value: MATCHING_METHOD_LABELS[matchingMethod] },
          {
            label: "Scope",
            value: mediaId
              ? (mediaItems ?? []).find((media) => media.id === mediaId)?.caption?.slice(0, 24) || "1 selected post/reel"
              : "All posts/reels",
          },
          { label: "Hide", value: hide ? "On" : "Off" },
          { label: "Delete", value: deleteComment ? "On" : "Off" },
        ]}
      />
      <TipsCallout
        tips={[
          "By default this automation checks every comment on every post/reel on this account - scope it to one post/reel below if you only want to moderate that one.",
          "Hiding keeps the comment visible only to its author and their friends; deleting removes it entirely.",
          "You can enable both Hide and Delete at the same time - Delete wins since the comment is gone.",
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
      title={isEditing ? "Edit Comment Moderation" : "New Comment Moderation"}
      description="Automatically hide or delete Instagram comments that match keywords you choose — for filtering spam or abuse."
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
            <span className="text-sm font-medium">Which comments?</span>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <OptionPickerCard
                title="All comments"
                description="Moderate every comment, regardless of what it says"
                selected={commentScope === "all"}
                onSelect={() => setCommentScope("all")}
              />
              <OptionPickerCard
                title="Specific keywords"
                description="Only moderate comments that match a keyword you choose"
                selected={commentScope === "keywords"}
                onSelect={() => setCommentScope("keywords")}
              />
            </div>
          </div>

          {commentScope === "keywords" && (
            <>
              <div className="flex flex-col gap-1.5">
                <label htmlFor="trigger_keywords" className="text-sm font-medium">
                  Trigger keywords
                </label>
                <Input
                  id="trigger_keywords"
                  placeholder="e.g. buy followers, http, scam"
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
              By default this applies to every post/reel on this account. Optionally scope it to just one.
            </p>
            {mediaLoading ? (
              <p className="text-xs text-muted-foreground">Loading posts/reels…</p>
            ) : (
              <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
                <button
                  type="button"
                  onClick={() => setMediaId(null)}
                  className={`flex aspect-square flex-col items-center justify-center gap-1 rounded-md border p-2 text-center text-xs transition-colors ${
                    mediaId === null ? "border-accent bg-accent-soft text-accent" : "border-border hover:bg-muted text-foreground"
                  }`}
                >
                  All posts/reels
                </button>
                {(mediaItems ?? []).map((media) => {
                  const thumbnail = media.thumbnail_url || media.media_url;
                  const selected = mediaId === media.id;
                  return (
                    <button
                      key={media.id}
                      type="button"
                      onClick={() => setMediaId(media.id)}
                      className={`flex aspect-square flex-col overflow-hidden rounded-md border transition-colors ${
                        selected ? "border-accent ring-2 ring-accent" : "border-border hover:bg-muted"
                      }`}
                      title={media.caption ?? media.media_type}
                    >
                      {thumbnail ? (
                        <img src={thumbnail} alt={media.caption ?? ""} className="h-full w-full object-cover" />
                      ) : (
                        <span className="flex h-full w-full items-center justify-center bg-muted p-1 text-[10px] text-muted-foreground">
                          {(media.caption ?? media.media_type).slice(0, 40)}
                        </span>
                      )}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {validationError && <p className="text-sm text-destructive">{validationError}</p>}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <ToggleSettingRow
            icon={EyeOff}
            label="Hide"
            description="Hides matching comments from public view on the post/reel"
            checked={hide}
            onCheckedChange={setHide}
          />

          <ToggleSettingRow
            icon={Trash2}
            label="Delete"
            description="Permanently deletes matching comments"
            checked={deleteComment}
            onCheckedChange={setDeleteComment}
          />

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
