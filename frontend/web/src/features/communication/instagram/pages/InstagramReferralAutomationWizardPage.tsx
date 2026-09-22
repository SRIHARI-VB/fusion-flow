import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AxiosError } from "axios";
import { Plus, Trash2 } from "lucide-react";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Textarea } from "@fusion-flow/ui";
import { SummarySidebar, TipsCallout, WizardShell } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import type { InstagramReferralAutomationConfig, InstagramReferralRule } from "../types";

/** Backend automation type key for `POST /api/v1/predefined-automations` -
 * kept local to this file (not the shared `constants.ts`) per this
 * automation's scope. */
const INSTAGRAM_REFERRAL_AUTOMATION_TYPE = "instagram.referral_automation";

function emptyRule(): InstagramReferralRule {
  return { ref_match: "", reply_text: "" };
}

/**
 * `/communication/instagram/referral-automations/new` and
 * `/communication/instagram/referral-automations/:id/edit` (routed by the
 * coordinator's wiring) - the "Ad/Link Campaign Router" wizard: send a
 * different DM reply depending on which ad or ig.me shortlink started the
 * conversation, matched by a substring of Meta's `ref` parameter, falling
 * back to an optional default reply. Single-step by design - unlike the
 * keyword-based Instagram wizards, there's no natural "matching vs.
 * response" split here since each rule row already carries both its own
 * match and its own reply.
 */
export function InstagramReferralAutomationWizardPage() {
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
    foundAutomation && foundAutomation.automation_type === INSTAGRAM_REFERRAL_AUTOMATION_TYPE
      ? foundAutomation
      : undefined;

  const [rules, setRules] = useState<InstagramReferralRule[]>([emptyRule()]);
  const [defaultReplyText, setDefaultReplyText] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  // Seeds form state from the fetched automation exactly once, when
  // editing - guarded by `initialized` so a background refetch (e.g. the
  // list's polling) never clobbers what the tenant is mid-typing.
  useEffect(() => {
    if (!isEditing || initialized || !existingAutomation) return;
    const config = existingAutomation.config as InstagramReferralAutomationConfig;
    setRules(config.rules.length > 0 ? config.rules : [emptyRule()]);
    setDefaultReplyText(config.default_reply_text ?? "");
    setInitialized(true);
  }, [isEditing, initialized, existingAutomation]);

  const activeMutation = isEditing ? updateMutation : createMutation;
  const mutationError = activeMutation.error as AxiosError<{ detail?: string }> | null;

  function updateRule(index: number, patch: Partial<InstagramReferralRule>) {
    setRules((current) => current.map((rule, i) => (i === index ? { ...rule, ...patch } : rule)));
  }

  function addRule() {
    setRules((current) => [...current, emptyRule()]);
  }

  function removeRule(index: number) {
    setRules((current) => current.filter((_, i) => i !== index));
  }

  function handleSubmit() {
    const trimmedRules = rules.map((rule) => ({
      ref_match: rule.ref_match.trim(),
      reply_text: rule.reply_text.trim(),
    }));

    if (trimmedRules.length === 0) {
      setValidationError("Add at least one rule.");
      return;
    }
    if (trimmedRules.some((rule) => !rule.ref_match || !rule.reply_text)) {
      setValidationError("Every rule needs both a ref match and a reply.");
      return;
    }
    setValidationError(null);

    const trimmedDefault = defaultReplyText.trim();
    const config: InstagramReferralAutomationConfig = {
      rules: trimmedRules,
      default_reply_text: trimmedDefault ? trimmedDefault : null,
    };

    if (isEditing && id) {
      updateMutation.mutate(
        { id, config },
        { onSuccess: () => navigate("/communication/instagram/automations") },
      );
      return;
    }

    if (!instagramInstance) return;
    createMutation.mutate(
      {
        connector_instance_id: instagramInstance.id,
        automation_type: INSTAGRAM_REFERRAL_AUTOMATION_TYPE,
        name: trimmedRules.map((rule) => rule.ref_match).join(", "),
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
            You need a connected Instagram account before you can set up an ad/link campaign router.
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
          { label: "Rules", value: String(rules.length) },
          { label: "Fallback reply", value: defaultReplyText.trim() || "None" },
        ]}
      />
      <TipsCallout
        tips={[
          "The ref value is whatever your business set when creating the ad or ig.me shortlink in Meta's tools.",
          "Rules are checked in order, top to bottom - the first ref match wins.",
          "A rule matches on substring, not exact equality, so 'summer' also matches 'summer_sale_2026'.",
          "Leave the fallback reply blank to send nothing when no rule matches.",
        ]}
      />
    </>
  );

  const footer = (
    <>
      <Button variant="outline" onClick={() => navigate("/communication/instagram/automations")}>
        Cancel
      </Button>
      <Button onClick={handleSubmit} disabled={activeMutation.isPending}>
        {activeMutation.isPending ? "Saving…" : isEditing ? "Save Changes" : "Create Automation"}
      </Button>
    </>
  );

  return (
    <WizardShell
      title={isEditing ? "Edit Ad/Link Campaign Router" : "New Ad/Link Campaign Router"}
      description="Automatically send a different DM reply depending on which ad or ig.me shortlink a user came from."
      backTo="/communication/instagram/automations"
      backLabel="Back to automations"
      sidebar={sidebar}
      footer={footer}
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-3">
          <span className="text-sm font-medium">Rules</span>
          {rules.map((rule, index) => (
            <div key={index} className="flex flex-col gap-2 rounded-md border border-border p-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">Rule {index + 1}</span>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => removeRule(index)}
                  disabled={rules.length === 1}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor={`ref_match_${index}`} className="text-xs text-muted-foreground">
                  Ref contains
                </label>
                <Input
                  id={`ref_match_${index}`}
                  placeholder="e.g. summer_sale"
                  value={rule.ref_match}
                  onChange={(event) => updateRule(index, { ref_match: event.target.value })}
                />
              </div>

              <div className="flex flex-col gap-1.5">
                <label htmlFor={`reply_text_${index}`} className="text-xs text-muted-foreground">
                  Reply
                </label>
                <Textarea
                  id={`reply_text_${index}`}
                  rows={2}
                  placeholder="e.g. Check out our summer sale!"
                  value={rule.reply_text}
                  onChange={(event) => updateRule(index, { reply_text: event.target.value })}
                />
              </div>
            </div>
          ))}

          <Button type="button" variant="outline" onClick={addRule} className="self-start">
            <Plus className="mr-1 h-4 w-4" />
            Add Rule
          </Button>
        </div>

        <div className="flex flex-col gap-1.5">
          <label htmlFor="default_reply_text" className="text-sm font-medium">
            Fallback reply (optional)
          </label>
          <Textarea
            id="default_reply_text"
            rows={2}
            placeholder="Sent when no rule above matches"
            value={defaultReplyText}
            onChange={(event) => setDefaultReplyText(event.target.value)}
          />
          <p className="text-xs text-muted-foreground">Sent when no rule above matches.</p>
        </div>

        {mutationError && (
          <p className="text-sm text-destructive">
            {mutationError.response?.data?.detail ?? "Could not save this automation."}
          </p>
        )}
        {validationError && <p className="text-sm text-destructive">{validationError}</p>}
      </div>
    </WizardShell>
  );
}
