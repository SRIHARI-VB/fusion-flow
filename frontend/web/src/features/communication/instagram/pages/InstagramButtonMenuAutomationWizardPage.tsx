import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AxiosError } from "axios";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Textarea } from "@fusion-flow/ui";
import { OptionPickerCard, SummarySidebar, TipsCallout, WizardShell } from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import { MATCHING_METHOD_DESCRIPTIONS, MATCHING_METHOD_LABELS, MATCHING_METHODS } from "../constants";
import type { InstagramAutomationConfig, InstagramMatchingMethod } from "../types";

const INSTAGRAM_BUTTON_MENU_AUTOMATION_TYPE = "instagram.button_menu_automation";

const MAX_BUTTONS = 3;
const BUTTON_TITLE_MAX_LENGTH = 20; // Meta's button title length limit

/** A single tappable button: `title` is what's shown on the button,
 * `reply_text` is the DM sent back when it's tapped. */
interface InstagramMenuButton {
  title: string;
  reply_text: string;
}

/** `config` for `automation_type: "instagram.button_menu_automation"` -
 * kept local to this file rather than added to the shared `types.ts`
 * union, same convention as `InstagramMentionAutomationWizardPage.tsx`. */
interface InstagramButtonMenuAutomationConfig {
  trigger_keywords: string[];
  matching_method: InstagramMatchingMethod;
  menu_text: string;
  buttons: InstagramMenuButton[];
}

const STEPS = ["Keywords & Matching", "Menu & Buttons"];

/** Same "comma-separated field, trim/dedupe/drop-empties" UX as the DM
 * automation wizard - see `InstagramDmAutomationWizardPage.tsx`. */
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

function emptyButton(): InstagramMenuButton {
  return { title: "", reply_text: "" };
}

/**
 * `/communication/instagram/button-menu-automations/new` and
 * `/communication/instagram/button-menu-automations/:id/edit` - the
 * "Button Menu" wizard: reply to a keyword-matched DM with a text prompt
 * plus up to 3 tappable buttons, each sending its own configured reply
 * when tapped. Sibling to `InstagramDmAutomationWizardPage.tsx` for step 1,
 * but step 2 adds a dynamic buttons list instead of a single reply field.
 */
export function InstagramButtonMenuAutomationWizardPage() {
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
    foundAutomation && foundAutomation.automation_type === INSTAGRAM_BUTTON_MENU_AUTOMATION_TYPE
      ? foundAutomation
      : undefined;

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<InstagramMatchingMethod>("contains");
  const [menuText, setMenuText] = useState("");
  const [buttons, setButtons] = useState<InstagramMenuButton[]>([emptyButton()]);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!isEditing || initialized || !existingAutomation) return;
    const config = existingAutomation.config as unknown as InstagramButtonMenuAutomationConfig;
    setKeywordsInput(config.trigger_keywords.join(", "));
    setMatchingMethod(config.matching_method);
    setMenuText(config.menu_text);
    setButtons(config.buttons.length > 0 ? config.buttons : [emptyButton()]);
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

  function handleAddButton() {
    setButtons((current) => (current.length >= MAX_BUTTONS ? current : [...current, emptyButton()]));
  }

  function handleRemoveButton(index: number) {
    setButtons((current) => current.filter((_, i) => i !== index));
  }

  function handleButtonChange(index: number, field: keyof InstagramMenuButton, value: string) {
    setButtons((current) => current.map((button, i) => (i === index ? { ...button, [field]: value } : button)));
  }

  function handleSubmit() {
    const trimmedMenuText = menuText.trim();
    if (!trimmedMenuText) {
      setValidationError("Enter the menu prompt text.");
      return;
    }
    if (buttons.length === 0) {
      setValidationError("Add at least one button.");
      return;
    }
    const trimmedButtons = buttons.map((button) => ({
      title: button.title.trim(),
      reply_text: button.reply_text.trim(),
    }));
    const incomplete = trimmedButtons.some((button) => !button.title || !button.reply_text);
    if (incomplete) {
      setValidationError("Every button needs both a title and a reply text.");
      return;
    }
    setValidationError(null);

    const config: InstagramButtonMenuAutomationConfig = {
      trigger_keywords: keywords,
      matching_method: matchingMethod,
      menu_text: trimmedMenuText,
      buttons: trimmedButtons,
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
        automation_type: INSTAGRAM_BUTTON_MENU_AUTOMATION_TYPE,
        name: keywords.join(", "),
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
            You need a connected Instagram account before you can set up a button menu.
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
          { label: "Menu Text", value: menuText.trim() || "—" },
          {
            label: "Buttons",
            value: buttons.filter((button) => button.title.trim()).map((button) => button.title.trim()).join(", ") || "—",
          },
        ]}
      />
      <TipsCallout
        tips={[
          "This automation checks every direct message this account receives for the trigger keywords.",
          "Each button sends its own reply text the moment it's tapped - no further matching needed.",
          "Meta limits button titles to 20 characters and allows at most 3 buttons per message.",
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
      title={isEditing ? "Edit Button Menu" : "New Button Menu"}
      description="Reply to a trigger phrase with a menu of tappable buttons, each with its own follow-up response."
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
              placeholder="e.g. menu, help, options"
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
            <label htmlFor="menu_text" className="text-sm font-medium">
              Menu prompt
            </label>
            <Textarea
              id="menu_text"
              rows={3}
              placeholder="e.g. How can we help? Tap an option below."
              value={menuText}
              onChange={(event) => setMenuText(event.target.value)}
            />
          </div>

          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Buttons</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleAddButton}
                disabled={buttons.length >= MAX_BUTTONS}
              >
                + Add Button
              </Button>
            </div>

            {buttons.map((button, index) => (
              <div key={index} className="flex flex-col gap-2 rounded-md border border-border p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground">Button {index + 1}</span>
                  {buttons.length > 1 && (
                    <Button type="button" variant="ghost" size="sm" onClick={() => handleRemoveButton(index)}>
                      Remove
                    </Button>
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor={`button_title_${index}`} className="text-xs text-muted-foreground">
                    Button title (max {BUTTON_TITLE_MAX_LENGTH} characters)
                  </label>
                  <Input
                    id={`button_title_${index}`}
                    placeholder="e.g. Pricing"
                    maxLength={BUTTON_TITLE_MAX_LENGTH}
                    value={button.title}
                    onChange={(event) => handleButtonChange(index, "title", event.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor={`button_reply_${index}`} className="text-xs text-muted-foreground">
                    Reply sent when tapped
                  </label>
                  <Input
                    id={`button_reply_${index}`}
                    placeholder="e.g. Our pricing starts at..."
                    value={button.reply_text}
                    onChange={(event) => handleButtonChange(index, "reply_text", event.target.value)}
                  />
                </div>
              </div>
            ))}
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
