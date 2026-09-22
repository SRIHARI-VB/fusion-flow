import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AxiosError } from "axios";
import { EyeOff, Trash2 } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input } from "@fusion-flow/ui";
import { OptionPickerCard, SummarySidebar, TipsCallout, ToggleSettingRow, WizardShell } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import { MATCHING_METHOD_DESCRIPTIONS, MATCHING_METHOD_LABELS, MATCHING_METHODS } from "../constants";
import type { InstagramMatchingMethod } from "../types";

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
}

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
 * about replying to genuine engagement. Account-wide by design, same
 * reasoning as that wizard: there is no per-post scoping on the backend.
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
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<InstagramMatchingMethod>("contains");
  const [hide, setHide] = useState(false);
  const [deleteComment, setDeleteComment] = useState(false);
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
    setHide(config.hide);
    setDeleteComment(config.delete);
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
    if (!hide && !deleteComment) {
      setValidationError("Turn on at least one action - Hide or Delete - before saving.");
      return;
    }
    setValidationError(null);

    const config: InstagramCommentModerationConfig = {
      trigger_keywords: keywords,
      matching_method: matchingMethod,
      hide,
      delete: deleteComment,
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
        name: keywords.join(", "),
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
          { label: "Keywords", value: keywords.join(", ") },
          { label: "Matching Method", value: MATCHING_METHOD_LABELS[matchingMethod] },
          { label: "Hide", value: hide ? "On" : "Off" },
          { label: "Delete", value: deleteComment ? "On" : "Off" },
        ]}
      />
      <TipsCallout
        tips={[
          "This automation checks every comment on every post/reel connected to this account.",
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
