import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AxiosError } from "axios";
import { EyeOff, Heart } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { OptionPickerCard, SummarySidebar, TipsCallout, ToggleSettingRow, WizardShell } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import { MATCHING_METHOD_DESCRIPTIONS, MATCHING_METHOD_LABELS, MATCHING_METHODS } from "../constants";
import type { InstagramMatchingMethod } from "../types";

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
 * `/communication/instagram/automations/:id/edit` - the "Comment
 * Automation" wizard. Account-wide by design (fires on comments across
 * every post/reel on the connected Instagram account) - there is no
 * per-post scoping on the backend, so this deliberately has no
 * post-picker/preview step, unlike a hypothetical per-post automation.
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
  const existingAutomation = isEditing ? automations?.find((automation) => automation.id === id) : undefined;

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<InstagramMatchingMethod>("contains");
  const [autoLike, setAutoLike] = useState(false);
  const [autoHide, setAutoHide] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [dmText, setDmText] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  // Seeds form state from the fetched automation exactly once, when
  // editing - guarded by `initialized` so a background refetch (e.g. the
  // list's polling) never clobbers what the tenant is mid-typing.
  useEffect(() => {
    if (!isEditing || initialized || !existingAutomation) return;
    const config = existingAutomation.config;
    setKeywordsInput(config.trigger_keywords.join(", "));
    setMatchingMethod(config.matching_method);
    setAutoLike(config.auto_like);
    setAutoHide(config.auto_hide);
    setReplyText(config.reply_comment_text ?? "");
    setDmText(config.dm_text ?? "");
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
    const trimmedReply = replyText.trim();
    const trimmedDm = dmText.trim();
    if (!autoLike && !autoHide && !trimmedReply && !trimmedDm) {
      setValidationError(
        "Turn on at least one action - Auto-Like, Auto-Hide, a public reply, or a DM reply - before saving.",
      );
      return;
    }
    setValidationError(null);

    const config = {
      trigger_keywords: keywords,
      matching_method: matchingMethod,
      auto_like: autoLike,
      auto_hide: autoHide,
      reply_comment_text: trimmedReply || null,
      dm_text: trimmedDm || null,
    };

    if (isEditing && id) {
      updateMutation.mutate({ id, config }, { onSuccess: () => navigate("/communication/instagram/automations") });
      return;
    }

    if (!instagramInstance) return;
    createMutation.mutate(
      { connector_instance_id: instagramInstance.id, name: keywords.join(", "), config },
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

  const sidebar = (
    <>
      <SummarySidebar
        rows={[
          { label: "Keywords", value: keywords.join(", ") },
          { label: "Matching Method", value: MATCHING_METHOD_LABELS[matchingMethod] },
          { label: "Auto-Like", value: autoLike ? "On" : "Off" },
          { label: "Auto-Hide", value: autoHide ? "On" : "Off" },
          { label: "Public Reply", value: replyText.trim() || "Off" },
          { label: "DM Reply", value: dmText.trim() || "Off" },
        ]}
      />
      <TipsCallout
        tips={[
          "This automation checks every comment on every post/reel connected to this account.",
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
      description="Automatically like, hide, or reply to Instagram comments that match keywords you choose."
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

          {validationError && <p className="text-sm text-destructive">{validationError}</p>}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <ToggleSettingRow
            icon={Heart}
            label="Auto-Like"
            description="Automatically likes the matching comment"
            checked={autoLike}
            onCheckedChange={setAutoLike}
          />
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
