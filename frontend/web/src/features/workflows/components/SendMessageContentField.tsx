import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { Button, Input, Textarea, cn } from "@fusion-flow/ui";
import { useConnectorInstances } from "../../connectors/hooks";
import { InsertVariableMenu } from "./InsertVariableMenu";
import { MediaUploadButton } from "./MediaUploadButton";
import { LocationPreview, MediaThumb } from "./MediaPreview";

/**
 * Hand-written editor for `whatsapp.send_message`'s `content` config field -
 * a Pydantic discriminated union on `content_type` (text/media/location/
 * contact/template/buttons/list), same shape family as
 * `AskChoiceSourceField.tsx`'s `source` field and for the exact same reason
 * `jsonSchemaForm.ts`'s generic resolver can't express it. Follows that
 * file's precedent closely: a segmented content-type toggle, a per-type
 * sub-editor below it, and a `switchType` that replaces the whole value
 * with that type's own default shape rather than trying to carry over
 * incompatible fields from the previous type.
 *
 * `whatsapp.send_message` is fire-and-forget (no suspend, no per-option
 * output ports) - this component only edits the outbound payload shape,
 * nothing about branching/handles.
 */

export interface SendMessageContact {
  name: string;
  phone: string;
}

export interface SendMessageButton {
  id: string;
  title: string;
}

export interface SendMessageListRow {
  id: string;
  title: string;
  description?: string;
}

export interface SendMessageListSection {
  title: string;
  rows: SendMessageListRow[];
}

export type SendMessageContent =
  | { content_type: "text"; body: string }
  | {
      content_type: "media";
      media_type: "image" | "video" | "audio" | "document";
      media_url?: string;
      media_id?: string;
      caption?: string;
      filename?: string;
    }
  | { content_type: "location"; latitude: number; longitude: number; name?: string; address?: string }
  | { content_type: "contact"; contacts: SendMessageContact[] }
  | {
      content_type: "template";
      template_name: string;
      language_code: string;
      header_variable?: string;
      /** Mutually exclusive with `header_variable` - a template has a text
       * header OR a media header, never both (backend validates this). */
      header_media_type?: "image" | "video" | "document";
      header_media_url?: string;
      header_media_id?: string;
      body_variables: string[];
      /** NOT a way to author new buttons - WhatsApp template buttons are
       * fixed at Meta template-approval time. Each value supplies the
       * dynamic VALUE for a button already defined as a dynamic URL
       * placeholder on the approved template, in order. */
      button_url_params?: string[];
    }
  | { content_type: "buttons"; body_text: string; buttons: SendMessageButton[] }
  | { content_type: "list"; body_text: string; list_button_label: string; sections: SendMessageListSection[] };

type ContentType = SendMessageContent["content_type"];

export const DEFAULT_TEXT_CONTENT: Extract<SendMessageContent, { content_type: "text" }> = {
  content_type: "text",
  body: "",
};
const DEFAULT_MEDIA_CONTENT: Extract<SendMessageContent, { content_type: "media" }> = {
  content_type: "media",
  media_type: "image",
  media_url: "",
  media_id: "",
  caption: "",
  filename: "",
};
const DEFAULT_LOCATION_CONTENT: Extract<SendMessageContent, { content_type: "location" }> = {
  content_type: "location",
  latitude: 0,
  longitude: 0,
  name: "",
  address: "",
};
const DEFAULT_CONTACT_CONTENT: Extract<SendMessageContent, { content_type: "contact" }> = {
  content_type: "contact",
  contacts: [{ name: "", phone: "" }],
};
const DEFAULT_TEMPLATE_CONTENT: Extract<SendMessageContent, { content_type: "template" }> = {
  content_type: "template",
  template_name: "",
  language_code: "en_US",
  header_variable: "",
  header_media_type: undefined,
  header_media_url: "",
  header_media_id: "",
  body_variables: [],
  button_url_params: [],
};
const DEFAULT_BUTTONS_CONTENT: Extract<SendMessageContent, { content_type: "buttons" }> = {
  content_type: "buttons",
  body_text: "",
  buttons: [{ id: "", title: "" }],
};
const DEFAULT_LIST_CONTENT: Extract<SendMessageContent, { content_type: "list" }> = {
  content_type: "list",
  body_text: "",
  list_button_label: "",
  sections: [{ title: "", rows: [{ id: "", title: "", description: "" }] }],
};

const DEFAULTS_BY_TYPE: Record<ContentType, SendMessageContent> = {
  text: DEFAULT_TEXT_CONTENT,
  media: DEFAULT_MEDIA_CONTENT,
  location: DEFAULT_LOCATION_CONTENT,
  contact: DEFAULT_CONTACT_CONTENT,
  template: DEFAULT_TEMPLATE_CONTENT,
  buttons: DEFAULT_BUTTONS_CONTENT,
  list: DEFAULT_LIST_CONTENT,
};

const CONTENT_TYPE_OPTIONS: { value: ContentType; label: string }[] = [
  { value: "text", label: "Message" },
  { value: "media", label: "Media" },
  { value: "location", label: "Location" },
  { value: "contact", label: "Contact" },
  { value: "template", label: "Template" },
  { value: "buttons", label: "Buttons" },
  { value: "list", label: "List" },
];

const segmentBase =
  "flex-1 rounded-md border px-2 py-1.5 text-xs font-medium text-center transition-colors";
const segmentInactive = "border-border bg-background text-muted-foreground hover:border-accent";
const segmentActive = "border-accent bg-accent-soft text-foreground";

interface SendMessageContentFieldProps {
  value: SendMessageContent | undefined;
  onChange: (next: SendMessageContent) => void;
  upstreamSuggestions?: { path: string; label: string }[];
}

export function SendMessageContentField({ value, onChange, upstreamSuggestions = [] }: SendMessageContentFieldProps) {
  const contentType = value?.content_type ?? "text";

  function switchType(next: ContentType) {
    if (next === contentType) return;
    onChange(DEFAULTS_BY_TYPE[next]);
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-2">
      <div className="flex flex-wrap gap-1.5">
        {CONTENT_TYPE_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            className={cn(segmentBase, contentType === opt.value ? segmentActive : segmentInactive)}
            onClick={() => switchType(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {contentType === "text" && (
        <TextEditor
          value={value?.content_type === "text" ? value : DEFAULT_TEXT_CONTENT}
          onChange={onChange}
          upstreamSuggestions={upstreamSuggestions}
        />
      )}
      {contentType === "media" && (
        <MediaEditor value={value?.content_type === "media" ? value : DEFAULT_MEDIA_CONTENT} onChange={onChange} />
      )}
      {contentType === "location" && (
        <LocationEditor value={value?.content_type === "location" ? value : DEFAULT_LOCATION_CONTENT} onChange={onChange} />
      )}
      {contentType === "contact" && (
        <ContactEditor value={value?.content_type === "contact" ? value : DEFAULT_CONTACT_CONTENT} onChange={onChange} />
      )}
      {contentType === "template" && (
        <TemplateEditor value={value?.content_type === "template" ? value : DEFAULT_TEMPLATE_CONTENT} onChange={onChange} />
      )}
      {contentType === "buttons" && (
        <ButtonsEditor
          value={value?.content_type === "buttons" ? value : DEFAULT_BUTTONS_CONTENT}
          onChange={onChange}
          upstreamSuggestions={upstreamSuggestions}
        />
      )}
      {contentType === "list" && (
        <ListEditor
          value={value?.content_type === "list" ? value : DEFAULT_LIST_CONTENT}
          onChange={onChange}
          upstreamSuggestions={upstreamSuggestions}
        />
      )}
    </div>
  );
}

const BODY_MAX_LENGTH = 4096;

function TextEditor({
  value,
  onChange,
  upstreamSuggestions,
}: {
  value: Extract<SendMessageContent, { content_type: "text" }>;
  onChange: (next: SendMessageContent) => void;
  upstreamSuggestions: { path: string; label: string }[];
}) {
  const length = value.body?.length ?? 0;
  const overLimit = length > BODY_MAX_LENGTH;
  const nearLimit = !overLimit && length > BODY_MAX_LENGTH * 0.9;

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-start gap-1">
        <Textarea
          value={value.body}
          onChange={(e) => onChange({ ...value, body: e.target.value })}
          placeholder="Message text"
          rows={4}
        />
        <InsertVariableMenu
          suggestions={upstreamSuggestions}
          onInsert={(path) => onChange({ ...value, body: `${value.body ?? ""}{{${path}}}` })}
        />
      </div>
      <p
        className={cn(
          "text-right text-[11px]",
          overLimit ? "text-destructive" : nearLimit ? "text-amber-600" : "text-muted-foreground",
        )}
      >
        {length}/{BODY_MAX_LENGTH}
      </p>
    </div>
  );
}

const MEDIA_TYPES: Extract<SendMessageContent, { content_type: "media" }>["media_type"][] = [
  "image",
  "video",
  "audio",
  "document",
];

function MediaEditor({
  value,
  onChange,
}: {
  value: Extract<SendMessageContent, { content_type: "media" }>;
  onChange: (next: SendMessageContent) => void;
}) {
  const { data: connectorInstances = [] } = useConnectorInstances();
  const r2InstanceId = connectorInstances.find(
    (instance) => instance.connector_type_key === "cloudflare_r2" && instance.state === "connected",
  )?.id;
  // Which input the URL field below shows - purely a local view toggle, not
  // part of the saved config (there's only ever one real `media_url`).
  // Switching tabs never clears whatever's already in `media_url`/`media_id`
  // - only a successful upload (or manual edit) changes them.
  const [mediaSource, setMediaSource] = useState<"link" | "upload">("link");

  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-1.5">
        {MEDIA_TYPES.map((mt) => (
          <button
            key={mt}
            type="button"
            className={cn(segmentBase, value.media_type === mt ? segmentActive : segmentInactive)}
            onClick={() => onChange({ ...value, media_type: mt })}
          >
            {mt.charAt(0).toUpperCase() + mt.slice(1)}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] text-muted-foreground">Media source</label>
        <div className="flex gap-1.5">
          <button
            type="button"
            className={cn(segmentBase, mediaSource === "link" ? segmentActive : segmentInactive)}
            onClick={() => setMediaSource("link")}
          >
            Link
          </button>
          <button
            type="button"
            className={cn(segmentBase, mediaSource === "upload" ? segmentActive : segmentInactive)}
            onClick={() => setMediaSource("upload")}
          >
            Upload a file
          </button>
        </div>
        {mediaSource === "link" ? (
          <Input
            value={value.media_url ?? ""}
            onChange={(e) => onChange({ ...value, media_url: e.target.value })}
            placeholder="https://..."
          />
        ) : (
          <MediaUploadButton
            connectorInstanceId={r2InstanceId}
            onUploaded={(url) => onChange({ ...value, media_url: url })}
          />
        )}
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-muted-foreground">Or a previously uploaded media id</label>
        <Input
          value={value.media_id ?? ""}
          onChange={(e) => onChange({ ...value, media_id: e.target.value })}
          placeholder="media id"
        />
      </div>
      <p className="text-[11px] text-muted-foreground">Provide either a URL or a previously uploaded media id.</p>

      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-muted-foreground">Caption</label>
        <Input value={value.caption ?? ""} onChange={(e) => onChange({ ...value, caption: e.target.value })} />
      </div>

      {value.media_type === "document" && (
        <div className="flex flex-col gap-1">
          <label className="text-[11px] text-muted-foreground">Filename</label>
          <Input
            value={value.filename ?? ""}
            onChange={(e) => onChange({ ...value, filename: e.target.value })}
            placeholder="invoice.pdf"
          />
        </div>
      )}

      <MediaThumb
        mediaType={value.media_type}
        url={value.media_url}
        mediaId={value.media_id}
        filename={value.filename}
        size="md"
      />
    </div>
  );
}

function LocationEditor({
  value,
  onChange,
}: {
  value: Extract<SendMessageContent, { content_type: "location" }>;
  onChange: (next: SendMessageContent) => void;
}) {
  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-1">
          <label className="text-[11px] text-muted-foreground">Latitude</label>
          <Input
            type="number"
            step="any"
            value={value.latitude}
            onChange={(e) => onChange({ ...value, latitude: Number(e.target.value) || 0 })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <label className="text-[11px] text-muted-foreground">Longitude</label>
          <Input
            type="number"
            step="any"
            value={value.longitude}
            onChange={(e) => onChange({ ...value, longitude: Number(e.target.value) || 0 })}
          />
        </div>
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-muted-foreground">Name</label>
        <Input value={value.name ?? ""} onChange={(e) => onChange({ ...value, name: e.target.value })} />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-muted-foreground">Address</label>
        <Input value={value.address ?? ""} onChange={(e) => onChange({ ...value, address: e.target.value })} />
      </div>
      <LocationPreview latitude={value.latitude} longitude={value.longitude} name={value.name} address={value.address} size="md" />
    </div>
  );
}

function ContactEditor({
  value,
  onChange,
}: {
  value: Extract<SendMessageContent, { content_type: "contact" }>;
  onChange: (next: SendMessageContent) => void;
}) {
  const contacts = value.contacts ?? [];

  function update(index: number, patch: Partial<SendMessageContact>) {
    onChange({ ...value, contacts: contacts.map((c, i) => (i === index ? { ...c, ...patch } : c)) });
  }

  return (
    <div className="flex flex-col gap-2">
      {contacts.map((contact, index) => (
        <div key={index} className="flex items-center gap-1.5">
          <Input placeholder="Name" value={contact.name} onChange={(e) => update(index, { name: e.target.value })} />
          <Input
            placeholder="Phone (e.g. +15551234567)"
            value={contact.phone}
            onChange={(e) => update(index, { phone: e.target.value })}
          />
          <button
            type="button"
            aria-label="Remove contact"
            className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
            onClick={() => onChange({ ...value, contacts: contacts.filter((_, i) => i !== index) })}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => onChange({ ...value, contacts: [...contacts, { name: "", phone: "" }] })}
      >
        <Plus className="h-3.5 w-3.5" />
        Add contact
      </Button>
    </div>
  );
}

const TEMPLATE_HEADER_MEDIA_TYPES: Extract<
  SendMessageContent,
  { content_type: "template" }
>["header_media_type"][] = ["image", "video", "document"];

function TemplateEditor({
  value,
  onChange,
}: {
  value: Extract<SendMessageContent, { content_type: "template" }>;
  onChange: (next: SendMessageContent) => void;
}) {
  const bodyVariables = value.body_variables ?? [];
  const buttonUrlParams = value.button_url_params ?? [];
  // Default to "Text" for any already-saved config that predates media
  // headers (no `header_media_type` set yet).
  const headerKind: "text" | "media" = value.header_media_type ? "media" : "text";
  const { data: connectorInstances = [] } = useConnectorInstances();
  const r2InstanceId = connectorInstances.find(
    (instance) => instance.connector_type_key === "cloudflare_r2" && instance.state === "connected",
  )?.id;
  // Same local view-only toggle as `MediaEditor`'s `mediaSource` - which
  // input the header media URL field shows, not part of the saved config.
  const [headerMediaSource, setHeaderMediaSource] = useState<"link" | "upload">("link");

  function updateVariable(index: number, next: string) {
    onChange({ ...value, body_variables: bodyVariables.map((v, i) => (i === index ? next : v)) });
  }

  function updateButtonParam(index: number, next: string) {
    onChange({ ...value, button_url_params: buttonUrlParams.map((v, i) => (i === index ? next : v)) });
  }

  // Switching header kind clears whichever field set isn't active, so the
  // two never end up simultaneously populated (matches the backend's
  // mutual-exclusivity validator).
  function switchHeaderKind(next: "text" | "media") {
    if (next === headerKind) return;
    if (next === "text") {
      onChange({ ...value, header_media_type: undefined, header_media_url: "", header_media_id: "" });
    } else {
      onChange({ ...value, header_variable: "", header_media_type: "image" });
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-muted-foreground">Template name</label>
        <Input
          value={value.template_name}
          onChange={(e) => onChange({ ...value, template_name: e.target.value })}
          placeholder="order_confirmation"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-muted-foreground">Language code</label>
        <Input
          value={value.language_code}
          onChange={(e) => onChange({ ...value, language_code: e.target.value })}
          placeholder="en_US"
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] text-muted-foreground">Header</label>
        <div className="flex gap-1.5">
          <button
            type="button"
            className={cn(segmentBase, headerKind === "text" ? segmentActive : segmentInactive)}
            onClick={() => switchHeaderKind("text")}
          >
            Text
          </button>
          <button
            type="button"
            className={cn(segmentBase, headerKind === "media" ? segmentActive : segmentInactive)}
            onClick={() => switchHeaderKind("media")}
          >
            Media
          </button>
        </div>

        {headerKind === "text" ? (
          <Input
            value={value.header_variable ?? ""}
            onChange={(e) => onChange({ ...value, header_variable: e.target.value })}
            placeholder="Header variable (optional)"
          />
        ) : (
          <div className="flex flex-col gap-2 rounded-md border border-border p-2">
            <div className="flex gap-1.5">
              {TEMPLATE_HEADER_MEDIA_TYPES.map((mt) => (
                <button
                  key={mt}
                  type="button"
                  className={cn(segmentBase, value.header_media_type === mt ? segmentActive : segmentInactive)}
                  onClick={() => onChange({ ...value, header_media_type: mt })}
                >
                  {mt ? mt.charAt(0).toUpperCase() + mt.slice(1) : mt}
                </button>
              ))}
            </div>
            <div className="flex gap-1.5">
              <button
                type="button"
                className={cn(segmentBase, headerMediaSource === "link" ? segmentActive : segmentInactive)}
                onClick={() => setHeaderMediaSource("link")}
              >
                Link
              </button>
              <button
                type="button"
                className={cn(segmentBase, headerMediaSource === "upload" ? segmentActive : segmentInactive)}
                onClick={() => setHeaderMediaSource("upload")}
              >
                Upload a file
              </button>
            </div>
            {headerMediaSource === "link" ? (
              <Input
                value={value.header_media_url ?? ""}
                onChange={(e) => onChange({ ...value, header_media_url: e.target.value })}
                placeholder="https://..."
              />
            ) : (
              <MediaUploadButton
                connectorInstanceId={r2InstanceId}
                onUploaded={(url) => onChange({ ...value, header_media_url: url })}
              />
            )}
            <Input
              value={value.header_media_id ?? ""}
              onChange={(e) => onChange({ ...value, header_media_id: e.target.value })}
              placeholder="Or a previously uploaded media id"
            />
            <p className="text-[11px] text-muted-foreground">Provide either a URL or a previously uploaded media id.</p>
            <MediaThumb
              mediaType={value.header_media_type ?? "image"}
              url={value.header_media_url}
              mediaId={value.header_media_id}
              size="md"
            />
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] text-muted-foreground">Body variables (in order)</label>
        {bodyVariables.map((variable, index) => (
          <div key={index} className="flex items-center gap-1.5">
            <Input
              value={variable}
              onChange={(e) => updateVariable(index, e.target.value)}
              placeholder={`Variable ${index + 1}`}
            />
            <button
              type="button"
              aria-label="Remove variable"
              className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
              onClick={() => onChange({ ...value, body_variables: bodyVariables.filter((_, i) => i !== index) })}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange({ ...value, body_variables: [...bodyVariables, ""] })}
        >
          <Plus className="h-3.5 w-3.5" />
          Add variable
        </Button>
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-[11px] text-muted-foreground">Button link values</label>
        <p className="text-[11px] text-muted-foreground">
          One value per dynamic URL button already defined on this approved template, in order.
        </p>
        {buttonUrlParams.map((param, index) => (
          <div key={index} className="flex items-center gap-1.5">
            <Input
              value={param}
              onChange={(e) => updateButtonParam(index, e.target.value)}
              placeholder={`Button ${index + 1} link value`}
            />
            <button
              type="button"
              aria-label="Remove button link value"
              className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
              onClick={() =>
                onChange({ ...value, button_url_params: buttonUrlParams.filter((_, i) => i !== index) })
              }
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => onChange({ ...value, button_url_params: [...buttonUrlParams, ""] })}
        >
          <Plus className="h-3.5 w-3.5" />
          Add button link value
        </Button>
      </div>
    </div>
  );
}

const BUTTON_TITLE_MAX_LENGTH = 20;

function ButtonsEditor({
  value,
  onChange,
  upstreamSuggestions,
}: {
  value: Extract<SendMessageContent, { content_type: "buttons" }>;
  onChange: (next: SendMessageContent) => void;
  upstreamSuggestions: { path: string; label: string }[];
}) {
  const buttons = value.buttons ?? [];

  function update(index: number, patch: Partial<SendMessageButton>) {
    onChange({ ...value, buttons: buttons.map((b, i) => (i === index ? { ...b, ...patch } : b)) });
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-1">
        <Textarea
          value={value.body_text}
          onChange={(e) => onChange({ ...value, body_text: e.target.value })}
          placeholder="Message body"
          rows={3}
        />
        <InsertVariableMenu
          suggestions={upstreamSuggestions}
          onInsert={(path) => onChange({ ...value, body_text: `${value.body_text ?? ""}{{${path}}}` })}
        />
      </div>

      <div className="flex flex-col gap-2">
        {buttons.map((btn, index) => (
          <div key={index} className="flex items-center gap-1.5">
            <Input placeholder="id (e.g. yes)" value={btn.id} onChange={(e) => update(index, { id: e.target.value })} />
            <div className="flex flex-1 flex-col gap-0.5">
              <Input
                placeholder="Button title"
                maxLength={BUTTON_TITLE_MAX_LENGTH}
                value={btn.title}
                onChange={(e) => update(index, { title: e.target.value })}
              />
              <span
                className={cn(
                  "text-right text-[10px]",
                  btn.title.length >= BUTTON_TITLE_MAX_LENGTH ? "text-destructive" : "text-muted-foreground",
                )}
              >
                {btn.title.length}/{BUTTON_TITLE_MAX_LENGTH}
              </span>
            </div>
            <button
              type="button"
              aria-label="Remove button"
              className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
              onClick={() => onChange({ ...value, buttons: buttons.filter((_, i) => i !== index) })}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        ))}
        {buttons.length < 3 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => onChange({ ...value, buttons: [...buttons, { id: "", title: "" }] })}
          >
            <Plus className="h-3.5 w-3.5" />
            Add button
          </Button>
        )}
      </div>
      <p className="text-[11px] text-muted-foreground">Meta allows at most 3 quick-reply buttons.</p>
    </div>
  );
}

function ListEditor({
  value,
  onChange,
  upstreamSuggestions,
}: {
  value: Extract<SendMessageContent, { content_type: "list" }>;
  onChange: (next: SendMessageContent) => void;
  upstreamSuggestions: { path: string; label: string }[];
}) {
  const sections = value.sections ?? [];

  function updateSection(index: number, patch: Partial<SendMessageListSection>) {
    onChange({ ...value, sections: sections.map((s, i) => (i === index ? { ...s, ...patch } : s)) });
  }

  function removeSection(index: number) {
    onChange({ ...value, sections: sections.filter((_, i) => i !== index) });
  }

  function addSection() {
    onChange({
      ...value,
      sections: [...sections, { title: "", rows: [{ id: "", title: "", description: "" }] }],
    });
  }

  function updateRow(sectionIndex: number, rowIndex: number, patch: Partial<SendMessageListRow>) {
    const section = sections[sectionIndex];
    const rows = section.rows.map((r, i) => (i === rowIndex ? { ...r, ...patch } : r));
    updateSection(sectionIndex, { rows });
  }

  function removeRow(sectionIndex: number, rowIndex: number) {
    const section = sections[sectionIndex];
    updateSection(sectionIndex, { rows: section.rows.filter((_, i) => i !== rowIndex) });
  }

  function addRow(sectionIndex: number) {
    const section = sections[sectionIndex];
    updateSection(sectionIndex, { rows: [...section.rows, { id: "", title: "", description: "" }] });
  }

  const totalRows = sections.reduce((sum, s) => sum + s.rows.length, 0);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-start gap-1">
        <Textarea
          value={value.body_text}
          onChange={(e) => onChange({ ...value, body_text: e.target.value })}
          placeholder="Message body"
          rows={3}
        />
        <InsertVariableMenu
          suggestions={upstreamSuggestions}
          onInsert={(path) => onChange({ ...value, body_text: `${value.body_text ?? ""}{{${path}}}` })}
        />
      </div>

      <div className="flex flex-col gap-1">
        <label className="text-[11px] text-muted-foreground">List button label</label>
        <Input
          value={value.list_button_label}
          onChange={(e) => onChange({ ...value, list_button_label: e.target.value })}
          placeholder="e.g. View options"
        />
      </div>

      <div className="flex flex-col gap-2">
        {sections.map((section, sIndex) => (
          <div key={sIndex} className="flex flex-col gap-2 rounded-md border border-border p-2">
            <div className="flex items-center gap-1.5">
              <Input
                placeholder="Section title"
                value={section.title}
                onChange={(e) => updateSection(sIndex, { title: e.target.value })}
              />
              <button
                type="button"
                aria-label="Remove section"
                className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
                onClick={() => removeSection(sIndex)}
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </div>

            <div className="flex flex-col gap-1.5 border-l border-border pl-2">
              {section.rows.map((row, rIndex) => (
                <div key={rIndex} className="flex items-center gap-1.5">
                  <Input placeholder="id" value={row.id} onChange={(e) => updateRow(sIndex, rIndex, { id: e.target.value })} />
                  <Input
                    placeholder="Row title"
                    value={row.title}
                    onChange={(e) => updateRow(sIndex, rIndex, { title: e.target.value })}
                  />
                  <Input
                    placeholder="Description (optional)"
                    value={row.description ?? ""}
                    onChange={(e) => updateRow(sIndex, rIndex, { description: e.target.value })}
                  />
                  <button
                    type="button"
                    aria-label="Remove row"
                    className="shrink-0 rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-destructive"
                    onClick={() => removeRow(sIndex, rIndex)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              ))}
              <Button type="button" variant="outline" size="sm" onClick={() => addRow(sIndex)}>
                <Plus className="h-3.5 w-3.5" />
                Add row
              </Button>
            </div>
          </div>
        ))}
        <Button type="button" variant="outline" size="sm" onClick={addSection}>
          <Plus className="h-3.5 w-3.5" />
          Add section
        </Button>
      </div>
      <p className={cn("text-[11px]", totalRows > 10 ? "text-destructive" : "text-muted-foreground")}>
        WhatsApp caps interactive lists at 10 rows total across all sections ({totalRows}/10 so far).
      </p>
    </div>
  );
}
