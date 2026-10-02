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
import type { InstagramCommentMenuAutomationConfig, InstagramCommentMenuOption, InstagramMatchingMethod } from "../types";

const MAX_MENU_OPTIONS = 5;
const STEPS = ["Comment & Private Reply", "Menu & Ticket"];

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

function emptyOption(): InstagramCommentMenuOption {
  return { keyword: "", reply_text: "", media_url: null, media_type: null };
}

/**
 * `/communication/instagram/comment-menu-automations/new` and
 * `/communication/instagram/comment-menu-automations/:id/edit` - the
 * "Comment-to-DM Menu" wizard. A comment matching the trigger keyword(s)
 * (optionally scoped to specific posts/reels) gets a public reply plus a
 * Private Reply DM; replying to that DM with one of the configured menu
 * keywords gets its own text/media reply, except the designated "ticket"
 * keyword, which creates a support ticket and sends a confirmation
 * instead. See the backend's `instagram_comment_menu_automation.py`
 * module docstring for why this needs two separate message steps rather
 * than one rich DM (Meta's Send API can't address a first-time commenter
 * with anything but plain text).
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
  const [menuMatchingMethod, setMenuMatchingMethod] = useState<InstagramMatchingMethod>("contains");
  const [menuOptions, setMenuOptions] = useState<InstagramCommentMenuOption[]>([emptyOption()]);
  const [ticketKeyword, setTicketKeyword] = useState("");
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
    setMenuMatchingMethod(config.menu_matching_method);
    setMenuOptions(
      config.menu_options.length > 0
        ? config.menu_options.map((option) => ({
            keyword: option.keyword,
            reply_text: option.reply_text,
            media_url: option.media_url ?? null,
            media_type: option.media_type ?? null,
          }))
        : [emptyOption()],
    );
    setTicketKeyword(config.ticket_keyword);
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

  function handleAddOption() {
    setMenuOptions((current) => (current.length >= MAX_MENU_OPTIONS ? current : [...current, emptyOption()]));
  }

  function handleRemoveOption(index: number) {
    setMenuOptions((current) => current.filter((_, i) => i !== index));
  }

  function handleOptionChange(index: number, field: "keyword" | "reply_text", value: string) {
    setMenuOptions((current) => current.map((option, i) => (i === index ? { ...option, [field]: value } : option)));
  }

  function handleOptionMediaChange(index: number, media: SelectedMedia | null) {
    setMenuOptions((current) =>
      current.map((option, i) =>
        i === index
          ? {
              ...option,
              media_url: media?.url ?? null,
              media_type: media ? (media.content_type.startsWith("video") ? "video" : "image") : null,
            }
          : option,
      ),
    );
  }

  function handleSubmit() {
    const trimmedOptions = menuOptions.map((option) => ({
      keyword: option.keyword.trim(),
      reply_text: option.reply_text.trim(),
      media_url: option.media_url,
      media_type: option.media_type,
    }));
    const incomplete = trimmedOptions.some((option) => !option.keyword || !option.reply_text);
    if (incomplete) {
      setValidationError("Every menu option needs both a keyword and a reply text.");
      return;
    }
    const trimmedTicketKeyword = ticketKeyword.trim();
    const trimmedTicketSubject = ticketSubject.trim();
    const trimmedTicketConfirmation = ticketConfirmationText.trim();
    if (!trimmedTicketKeyword || !trimmedTicketSubject || !trimmedTicketConfirmation) {
      setValidationError("Fill in the ticket keyword, subject, and confirmation text.");
      return;
    }
    if (trimmedOptions.some((option) => option.keyword.toLowerCase() === trimmedTicketKeyword.toLowerCase())) {
      setValidationError("The ticket keyword must be different from every menu option's keyword.");
      return;
    }
    setValidationError(null);

    const config: InstagramCommentMenuAutomationConfig = {
      trigger_keywords: keywords,
      matching_method: matchingMethod,
      media_ids: mediaIds,
      reply_comment_text: replyCommentText.trim() || null,
      private_reply_text: privateReplyText.trim(),
      menu_matching_method: menuMatchingMethod,
      menu_options: trimmedOptions,
      ticket_keyword: trimmedTicketKeyword,
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
            label: "Menu Options",
            value: menuOptions.filter((o) => o.keyword.trim()).map((o) => o.keyword.trim()).join(", ") || "—",
          },
          { label: "Ticket Keyword", value: ticketKeyword.trim() || "—" },
        ]}
      />
      <TipsCallout
        tips={[
          "The Private Reply is the only message a first-time commenter can receive - Meta only allows plain text here, no images or buttons.",
          "Once they reply to that DM, a normal messaging window opens and the richer menu options (including media) become available.",
          "Keep the ticket keyword distinct from every other menu option so there's no ambiguity about which one creates a ticket.",
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
      description="Reply to a comment with a DM, then let the commenter choose a menu option by replying - one option can create a support ticket."
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
              placeholder="e.g. Thanks for your interest! Reply SERVICES, PRICING, or DEMO to learn more."
              value={privateReplyText}
              onChange={(event) => setPrivateReplyText(event.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Plain text only - this is the one message Meta allows to a commenter you've never messaged before.
            </p>
          </div>

          {validationError && <p className="text-sm text-destructive">{validationError}</p>}
        </div>
      ) : (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">Menu reply matching method</span>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {MATCHING_METHODS.map((method) => (
                <OptionPickerCard
                  key={method}
                  title={MATCHING_METHOD_LABELS[method]}
                  description={MATCHING_METHOD_DESCRIPTIONS[method]}
                  selected={menuMatchingMethod === method}
                  onSelect={() => setMenuMatchingMethod(method)}
                />
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Menu options</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleAddOption}
                disabled={menuOptions.length >= MAX_MENU_OPTIONS}
              >
                + Add Option
              </Button>
            </div>

            {menuOptions.map((option, index) => (
              <div key={index} className="flex flex-col gap-2 rounded-md border border-border p-3">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground">Option {index + 1}</span>
                  {menuOptions.length > 1 && (
                    <Button type="button" variant="ghost" size="sm" onClick={() => handleRemoveOption(index)}>
                      Remove
                    </Button>
                  )}
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor={`option_keyword_${index}`} className="text-xs text-muted-foreground">
                    Reply keyword
                  </label>
                  <Input
                    id={`option_keyword_${index}`}
                    placeholder="e.g. services"
                    value={option.keyword}
                    onChange={(event) => handleOptionChange(index, "keyword", event.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor={`option_reply_${index}`} className="text-xs text-muted-foreground">
                    Reply text
                  </label>
                  <Input
                    id={`option_reply_${index}`}
                    placeholder="e.g. We offer X, Y, Z."
                    value={option.reply_text}
                    onChange={(event) => handleOptionChange(index, "reply_text", event.target.value)}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <span className="text-xs text-muted-foreground">Attach media (optional)</span>
                  <MediaPicker
                    value={option.media_url ? { url: option.media_url, content_type: option.media_type ?? "image" } : null}
                    onChange={(media) => handleOptionMediaChange(index, media)}
                    accept="image,video"
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-col gap-2 rounded-md border border-border p-3">
            <span className="text-sm font-medium">Ticket-creating option</span>
            <p className="text-xs text-muted-foreground">
              Replying with this keyword creates a support ticket instead of a plain text reply.
            </p>
            <div className="flex flex-col gap-1.5">
              <label htmlFor="ticket_keyword" className="text-xs text-muted-foreground">
                Reply keyword
              </label>
              <Input
                id="ticket_keyword"
                placeholder="e.g. demo"
                value={ticketKeyword}
                onChange={(event) => setTicketKeyword(event.target.value)}
              />
            </div>
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
