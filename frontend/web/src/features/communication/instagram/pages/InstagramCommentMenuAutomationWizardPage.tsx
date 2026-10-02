import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AxiosError } from "axios";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Textarea } from "@fusion-flow/ui";
import {
  MediaPicker,
  OptionPickerCard,
  PostReelMultiPicker,
  SummarySidebar,
  TipsCallout,
  WizardShell,
  type SelectedMedia,
} from "../../wizard";
import { useConnectorInstances } from "../../../connectors/hooks";
import { useCreateInstagramAutomation, useInstagramAutomations, useUpdateInstagramAutomation } from "../hooks";
import {
  INSTAGRAM_COMMENT_MENU_AUTOMATION_TYPE,
  MATCHING_METHOD_DESCRIPTIONS,
  MATCHING_METHOD_LABELS,
  MATCHING_METHODS,
} from "../constants";
import type { InstagramCommentMenuAutomationConfig, InstagramCommentMenuButton, InstagramMatchingMethod } from "../types";

const MAX_BUTTONS = 3; // Meta's own button-template cap
const BUTTON_TITLE_MAX_LENGTH = 20; // Meta's button title length limit
const STEPS = ["Comment & Private Reply", "Button Menu"];

/** Same "comma-separated field, trim/dedupe/drop-empties" UX as every
 * other Instagram automation wizard. */
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

function emptyButton(): InstagramCommentMenuButton {
  return { title: "", reply_text: "", media_url: null, media_type: null, is_ticket_button: false };
}

/**
 * `/communication/instagram/comment-menu-automations/new` and
 * `/communication/instagram/comment-menu-automations/:id/edit` - the
 * "Comment-to-DM Menu" wizard. A comment matching the trigger keyword(s)
 * (optionally scoped to specific posts/reels) gets a public reply plus a
 * Private Reply DM; once the commenter replies with anything at all, a
 * real tappable button menu is sent - no free-typing involved. One
 * button creates a support ticket instead of replying with text. See the
 * backend's `instagram_comment_menu_automation.py` module docstring for
 * why this needs three separate message steps rather than one rich DM
 * (Meta's Send API can't address a first-time commenter with anything
 * but plain text, and a button tap always starts a fresh trigger chain,
 * never resumes the one that sent it).
 */
export function InstagramCommentMenuAutomationWizardPage() {
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
    foundAutomation && foundAutomation.automation_type === INSTAGRAM_COMMENT_MENU_AUTOMATION_TYPE
      ? foundAutomation
      : undefined;

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [keywordsInput, setKeywordsInput] = useState("");
  const [matchingMethod, setMatchingMethod] = useState<InstagramMatchingMethod>("contains");
  const [mediaIds, setMediaIds] = useState<string[]>([]);
  const [replyCommentText, setReplyCommentText] = useState("");
  const [privateReplyText, setPrivateReplyText] = useState("");
  const [menuText, setMenuText] = useState("");
  const [buttons, setButtons] = useState<InstagramCommentMenuButton[]>([emptyButton()]);
  const [ticketSubject, setTicketSubject] = useState("");
  const [ticketConfirmationText, setTicketConfirmationText] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!isEditing || initialized || !existingAutomation) return;
    const config = existingAutomation.config as InstagramCommentMenuAutomationConfig;
    setKeywordsInput(config.trigger_keywords.join(", "));
    setMatchingMethod(config.matching_method);
    setMediaIds(config.media_ids ?? []);
    setReplyCommentText(config.reply_comment_text ?? "");
    setPrivateReplyText(config.private_reply_text);
    setMenuText(config.menu_text);
    setButtons(
      config.buttons.length > 0
        ? config.buttons.map((button) => ({
            title: button.title,
            reply_text: button.reply_text,
            media_url: button.media_url ?? null,
            media_type: button.media_type ?? null,
            is_ticket_button: button.is_ticket_button,
          }))
        : [emptyButton()],
    );
    setTicketSubject(config.ticket_subject);
    setTicketConfirmationText(config.ticket_confirmation_text);
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
    if (!privateReplyText.trim()) {
      setValidationError("Enter the Private Reply DM text - this is the only message a first-time commenter can receive.");
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

  function handleButtonChange(index: number, field: "title" | "reply_text", value: string) {
    setButtons((current) => current.map((button, i) => (i === index ? { ...button, [field]: value } : button)));
  }

  function handleButtonMediaChange(index: number, media: SelectedMedia | null) {
    setButtons((current) =>
      current.map((button, i) =>
        i === index
          ? {
              ...button,
              media_url: media?.url ?? null,
              media_type: media ? (media.content_type.startsWith("video") ? "video" : "image") : null,
            }
          : button,
      ),
    );
  }

  function handleSetTicketButton(index: number) {
    setButtons((current) => current.map((button, i) => ({ ...button, is_ticket_button: i === index })));
  }

  function handleSubmit() {
    const trimmedButtons = buttons.map((button) => ({
      title: button.title.trim(),
      reply_text: button.is_ticket_button ? null : button.reply_text?.trim() || "",
      media_url: button.media_url,
      media_type: button.media_type,
      is_ticket_button: button.is_ticket_button,
    }));
    const missingTitle = trimmedButtons.some((button) => !button.title);
    if (missingTitle) {
      setValidationError("Every button needs a title.");
      return;
    }
    const ticketButtons = trimmedButtons.filter((button) => button.is_ticket_button);
    if (ticketButtons.length !== 1) {
      setValidationError("Mark exactly one button as the ticket-creating option.");
      return;
    }
    const missingReply = trimmedButtons.some((button) => !button.is_ticket_button && !button.reply_text);
    if (missingReply) {
      setValidationError("Every non-ticket button needs a reply text.");
      return;
    }
    const trimmedMenuText = menuText.trim();
    const trimmedTicketSubject = ticketSubject.trim();
    const trimmedTicketConfirmation = ticketConfirmationText.trim();
    if (!trimmedMenuText || !trimmedTicketSubject || !trimmedTicketConfirmation) {
      setValidationError("Fill in the menu prompt, ticket subject, and ticket confirmation text.");
      return;
    }
    setValidationError(null);

    const config: InstagramCommentMenuAutomationConfig = {
      trigger_keywords: keywords,
      matching_method: matchingMethod,
      media_ids: mediaIds,
      reply_comment_text: replyCommentText.trim() || null,
      private_reply_text: privateReplyText.trim(),
      menu_text: trimmedMenuText,
      buttons: trimmedButtons,
      ticket_subject: trimmedTicketSubject,
      ticket_confirmation_text: trimmedTicketConfirmation,
    };

    if (isEditing && id) {
      updateMutation.mutate({ id, config }, { onSuccess: () => navigate("/communication/instagram/automations") });
      return;
    }

    if (!instagramInstance) return;
    createMutation.mutate(
      {
        connector_instance_id: instagramInstance.id,
        automation_type: INSTAGRAM_COMMENT_MENU_AUTOMATION_TYPE,
        name: keywords.join(", "),
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
            You need a connected Instagram account before you can set up a comment-to-DM menu.
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
          { label: "Comment Keywords", value: keywords.join(", ") || "—" },
          { label: "Matching Method", value: MATCHING_METHOD_LABELS[matchingMethod] },
          { label: "Scope", value: mediaIds.length > 0 ? `${mediaIds.length} post(s)/reel(s)` : "All posts/reels" },
          { label: "Public Reply", value: replyCommentText.trim() || "Off" },
          { label: "Private Reply", value: privateReplyText.trim() || "—" },
          {
            label: "Buttons",
            value: buttons.filter((b) => b.title.trim()).map((b) => b.title.trim()).join(", ") || "—",
          },
        ]}
      />
      <TipsCallout
        tips={[
          "The Private Reply is the only message a first-time commenter can receive - Meta only allows plain text here, no buttons.",
          "Once they reply to that DM (anything at all), a real tappable button menu is sent - no typing needed from there.",
          "Mark exactly one button as the ticket-creating option - tapping it opens a support ticket instead of replying with text.",
          "This is a demo-account-friendly design: any inbound DM to this account shows the menu, not just replies to this flow's own Private Reply.",
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
      title={isEditing ? "Edit Comment-to-DM Menu" : "New Comment-to-DM Menu"}
      description="Reply to a comment with a DM, then send a real tappable button menu once they reply - one button can create a support ticket."
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
              placeholder="e.g. demo"
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

          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">Scope</span>
            <p className="text-xs text-muted-foreground">
              Apply this automation to every post/reel, or scope it to one or more specific ones.
            </p>
            <PostReelMultiPicker instanceId={instagramInstance?.id} value={mediaIds} onChange={setMediaIds} />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="reply_comment_text" className="text-sm font-medium">
              Public reply <span className="text-muted-foreground">(optional)</span>
            </label>
            <Input
              id="reply_comment_text"
              placeholder="e.g. Thanks! Check your DMs 📩"
              value={replyCommentText}
              onChange={(event) => setReplyCommentText(event.target.value)}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="private_reply_text" className="text-sm font-medium">
              Private Reply (DM)
            </label>
            <Textarea
              id="private_reply_text"
              rows={3}
              placeholder="e.g. Thanks for your interest! Reply here and I'll show you quick options."
              value={privateReplyText}
              onChange={(event) => setPrivateReplyText(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Plain text only - this is the one message Meta allows to a commenter you've never messaged before.
              Invite them to reply with anything; don't ask them to type a specific word.
            </p>
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
              placeholder="e.g. What would you like to know?"
              value={menuText}
              onChange={(event) => setMenuText(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Sent alongside the tappable buttons as soon as the commenter replies to the Private Reply.
            </p>
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

                <label className="flex items-center gap-2 text-xs text-muted-foreground">
                  <input
                    type="checkbox"
                    className="h-4 w-4 rounded border-input accent-accent"
                    checked={button.is_ticket_button}
                    onChange={() => handleSetTicketButton(index)}
                  />
                  This button creates a support ticket instead of replying with text
                </label>

                {!button.is_ticket_button && (
                  <>
                    <div className="flex flex-col gap-1.5">
                      <label htmlFor={`button_reply_${index}`} className="text-xs text-muted-foreground">
                        Reply sent when tapped
                      </label>
                      <Input
                        id={`button_reply_${index}`}
                        placeholder="e.g. Our pricing starts at..."
                        value={button.reply_text ?? ""}
                        onChange={(event) => handleButtonChange(index, "reply_text", event.target.value)}
                      />
                    </div>
                    <div className="flex flex-col gap-1.5">
                      <span className="text-xs text-muted-foreground">Attach media (optional)</span>
                      <MediaPicker
                        value={
                          button.media_url ? { url: button.media_url, content_type: button.media_type ?? "image" } : null
                        }
                        onChange={(media) => handleButtonMediaChange(index, media)}
                        accept="image,video"
                      />
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-2 rounded-md border border-border p-3">
            <span className="text-sm font-medium">Ticket details</span>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="ticket_subject" className="text-xs text-muted-foreground">
                Ticket subject
              </label>
              <Input
                id="ticket_subject"
                placeholder="e.g. Instagram demo request from {{trigger.from}}"
                value={ticketSubject}
                onChange={(event) => setTicketSubject(event.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="ticket_confirmation_text" className="text-xs text-muted-foreground">
                Confirmation DM
              </label>
              <Input
                id="ticket_confirmation_text"
                placeholder="e.g. Thanks! We've logged this and our team will reach out."
                value={ticketConfirmationText}
                onChange={(event) => setTicketConfirmationText(event.target.value)}
              />
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
