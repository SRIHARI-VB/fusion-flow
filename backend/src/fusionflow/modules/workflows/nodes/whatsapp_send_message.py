"""`whatsapp.send_message` — one unified "send a message" node replacing
the 7 separate WhatsApp send node types this product shipped with pre-
launch (`send_whatsapp_message`, `whatsapp.send_media`,
`whatsapp.send_location`, `whatsapp.send_contact`, `whatsapp.send_template`,
`whatsapp.send_interactive_buttons`, `whatsapp.send_interactive_list`).
Since there is no live tenant data yet, this is a direct replacement, not
a backward-compatible migration — the 7 old node types no longer exist.

The single `content` field is a Pydantic discriminated union on
`content_type` (`TextContent | MediaContent | LocationContent |
ContactContent | TemplateContent | ButtonsContent | ListContent`) — the
exact same shape this codebase already established for
`whatsapp.ask_choice`'s `source` field (`StaticSource | ModuleSource`,
discriminated on `kind`; see that node's module docstring). Each
`*Content` model carries EXACTLY the fields its corresponding original
node type had (same names, same validators/limits) — this is a
restructuring of 7 sibling nodes into 7 sibling branches of one node, not
a redesign of any of their individual behaviors.

All 7 originals were plain, non-suspending, `Success`-only actions
(`retryable=True`, `max_retries=2`, `required_connector_type_key=
"whatsapp"`, no `output_handles`/`can_suspend`) — this merged node keeps
that exact contract. In particular, `ButtonsContent`/`ListContent` are
still fire-and-forget sends with no per-option output ports; branching on
which button/row a customer tapped is `whatsapp.ask_choice`'s job (a
suspending node), not this one's — see that node's module docstring for
why a node can never suspend-to-ask and branch on its own answer.

`ButtonEntry`/`ListSection` (the `buttons`/`sections` row shapes) live in
`_whatsapp_common.py`, shared with `whatsapp.ask_question`, rather than
being redefined here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from fusionflow.modules.connectors.whatsapp.adapter import adapter as whatsapp_adapter
from fusionflow.modules.connectors.whatsapp.models import WhatsAppTemplate
from fusionflow.modules.workflows.engine.registry import (
    ExecutionContext,
    Failure,
    NodeExecutor,
    NodeResult,
    Success,
    node_executor_registry,
)
from fusionflow.modules.workflows.engine.templating import interpolate
from fusionflow.modules.workflows.nodes._whatsapp_common import ButtonEntry, ListSection, resolve_whatsapp_instance


class TextContent(BaseModel):
    content_type: Literal["text"] = "text"
    body: str = Field(
        min_length=1,
        max_length=4096,
        description="Message text. WhatsApp's own session-message body limit. May reference the run context, e.g. 'Thanks {{trigger.from}}!'.",
        json_schema_extra={"format": "textarea"},
    )


class MediaContent(BaseModel):
    content_type: Literal["media"] = "media"
    media_type: Literal["image", "video", "audio", "document"]
    media_url: str | None = Field(default=None, description="Publicly reachable URL - required unless media_id is set.")
    media_id: str | None = Field(default=None, description="A media id already uploaded to WhatsApp - alternative to media_url.")
    caption: str | None = Field(
        default=None, description="Not supported for audio.", json_schema_extra={"format": "textarea"}
    )
    filename: str | None = Field(default=None, description="Document filename shown to the recipient.")

    @model_validator(mode="after")
    def _require_url_or_id(self) -> "MediaContent":
        if not self.media_url and not self.media_id:
            raise ValueError("either media_url or media_id is required")
        return self


class LocationContent(BaseModel):
    content_type: Literal["location"] = "location"
    latitude: float
    longitude: float
    name: str | None = Field(default=None, description="Optional location name, e.g. a store name.")
    address: str | None = None


class ContactEntry(BaseModel):
    name: str = Field(min_length=1)
    phone: str = Field(min_length=1)


class ContactContent(BaseModel):
    content_type: Literal["contact"] = "contact"
    contacts: list[ContactEntry] = Field(min_length=1)


class TemplateContent(BaseModel):
    content_type: Literal["template"] = "template"
    template_name: str = Field(min_length=1)
    language_code: str = Field(min_length=1, description="e.g. 'en_US' - must match the approved template exactly.")
    header_variable: str | None = Field(default=None, description="Only if the template's header has a {{1}} placeholder.")
    # A template header is either plain text (`header_variable` above) or
    # media - never both. `header_media_type` + one of `header_media_url`/
    # `header_media_id` models a real WhatsApp marketing template's image/
    # video/document header (Meta's real Graph API component shape, same
    # `{"link":...}`/`{"id":...}` pattern as `MediaContent`'s own media).
    header_media_type: Literal["image", "video", "document"] | None = None
    header_media_url: str | None = None
    header_media_id: str | None = None
    body_variables: list[str] = Field(default_factory=list, description="In order, one per {{n}} placeholder in the body.")
    # NOT a way to author new buttons - WhatsApp template buttons are fixed
    # at Meta template-approval time. Each value supplies the dynamic VALUE
    # for a button already defined as a dynamic URL placeholder on the
    # approved template, in order.
    button_url_params: list[str] | None = None

    @model_validator(mode="after")
    def _validate_header(self) -> "TemplateContent":
        if self.header_variable and self.header_media_type:
            raise ValueError("set either header_variable or header_media_type, not both")
        if self.header_media_type and not self.header_media_url and not self.header_media_id:
            raise ValueError("header_media_type requires either header_media_url or header_media_id")
        return self


class ButtonsContent(BaseModel):
    content_type: Literal["buttons"] = "buttons"
    body_text: str = Field(min_length=1, json_schema_extra={"format": "textarea"})
    buttons: list[ButtonEntry] = Field(min_length=1, max_length=3, description="Meta allows at most 3 quick-reply buttons.")


class ListContent(BaseModel):
    content_type: Literal["list"] = "list"
    body_text: str = Field(min_length=1, json_schema_extra={"format": "textarea"})
    list_button_label: str = Field(min_length=1, max_length=20, default="Choose")
    sections: list[ListSection] = Field(min_length=1)

    @model_validator(mode="after")
    def _limit_total_rows(self) -> "ListContent":
        total_rows = sum(len(s.rows) for s in self.sections)
        if total_rows > 10:
            raise ValueError(f"Meta allows at most 10 rows total across all sections, got {total_rows}")
        return self


class SendMessageConfig(BaseModel):
    connector_instance_id: str = Field(min_length=1)
    to: str = Field(
        min_length=1,
        description="Recipient phone number, typically '{{trigger.from}}'.",
        json_schema_extra={"format": "recipient"},
    )
    content: TextContent | MediaContent | LocationContent | ContactContent | TemplateContent | ButtonsContent | ListContent = Field(
        discriminator="content_type"
    )


class SendMessageExecutor(NodeExecutor):
    node_type = "whatsapp.send_message"
    kind = "action"
    category = "Messages"
    icon = "message-circle"
    label = "Send a Message"
    description = (
        "Sends a message to the customer - plain text, media, location, a contact card, a template, "
        "or interactive buttons/list."
    )
    config_model = SendMessageConfig
    required_connector_type_key = "whatsapp"
    retryable = True
    max_retries = 2

    async def execute(self, context: ExecutionContext) -> NodeResult:
        config = SendMessageConfig.model_validate(context.config)
        to = interpolate(config.to, context.variables)

        instance = await resolve_whatsapp_instance(context, config.connector_instance_id)
        if isinstance(instance, Failure):
            return instance

        content = config.content

        if isinstance(content, TextContent):
            body = interpolate(content.body, context.variables)
            await whatsapp_adapter.send_text_message(instance=instance, to=to, body=body, session=context.session)
            return Success(output={"to": to, "content_type": "text", "body": body})

        if isinstance(content, MediaContent):
            media_url = interpolate(content.media_url, context.variables) if content.media_url else None
            caption = interpolate(content.caption, context.variables) if content.caption else None
            await whatsapp_adapter.send_media_message(
                instance=instance,
                to=to,
                media_type=content.media_type,
                media_url=media_url,
                media_id=content.media_id,
                caption=caption,
                filename=content.filename,
                session=context.session,
            )
            return Success(output={"to": to, "content_type": "media", "media_type": content.media_type})

        if isinstance(content, LocationContent):
            name = interpolate(content.name, context.variables) if content.name else None
            address = interpolate(content.address, context.variables) if content.address else None
            await whatsapp_adapter.send_location_message(
                instance=instance,
                to=to,
                latitude=content.latitude,
                longitude=content.longitude,
                name=name,
                address=address,
                session=context.session,
            )
            return Success(
                output={
                    "to": to,
                    "content_type": "location",
                    "latitude": content.latitude,
                    "longitude": content.longitude,
                }
            )

        if isinstance(content, ContactContent):
            await whatsapp_adapter.send_contact_message(
                instance=instance,
                to=to,
                contacts=[{"name": c.name, "phone": c.phone} for c in content.contacts],
                session=context.session,
            )
            return Success(output={"to": to, "content_type": "contact", "contact_count": len(content.contacts)})

        if isinstance(content, TemplateContent):
            header_variable = (
                interpolate(content.header_variable, context.variables) if content.header_variable else None
            )
            header_media_url = (
                interpolate(content.header_media_url, context.variables) if content.header_media_url else None
            )
            header_media_id = (
                interpolate(content.header_media_id, context.variables) if content.header_media_id else None
            )
            body_variables = [interpolate(v, context.variables) for v in content.body_variables]
            button_url_params = (
                [interpolate(v, context.variables) for v in content.button_url_params]
                if content.button_url_params
                else None
            )

            local_template = (
                await context.session.execute(
                    select(WhatsAppTemplate).where(
                        WhatsAppTemplate.connector_instance_id == instance.id,
                        WhatsAppTemplate.name == content.template_name,
                        WhatsAppTemplate.language == content.language_code,
                    )
                )
            ).scalar_one_or_none()
            if local_template is not None:
                expected_count = (local_template.components.get("body") or {}).get("variable_count")
                if expected_count is not None and expected_count != len(body_variables):
                    return Failure(
                        f"template {content.template_name!r} ({content.language_code}) expects "
                        f"{expected_count} body variable(s), got {len(body_variables)}"
                    )

            await whatsapp_adapter.send_template_message(
                instance=instance,
                to=to,
                template_name=content.template_name,
                language_code=content.language_code,
                header_variable=header_variable,
                header_media_type=content.header_media_type,
                header_media_url=header_media_url,
                header_media_id=header_media_id,
                body_variables=body_variables,
                button_url_params=button_url_params,
                session=context.session,
            )
            return Success(output={"to": to, "content_type": "template", "template_name": content.template_name})

        if isinstance(content, ButtonsContent):
            body_text = interpolate(content.body_text, context.variables)
            await whatsapp_adapter.send_interactive_message(
                instance=instance,
                to=to,
                body_text=body_text,
                interactive_type="button",
                buttons=[{"id": b.id, "title": b.title} for b in content.buttons],
                session=context.session,
            )
            return Success(output={"to": to, "content_type": "buttons", "button_count": len(content.buttons)})

        # ListContent - the only remaining branch.
        body_text = interpolate(content.body_text, context.variables)
        sections_payload = [
            {
                "title": section.title,
                "rows": [{"id": r.id, "title": r.title, "description": r.description} for r in section.rows],
            }
            for section in content.sections
        ]
        await whatsapp_adapter.send_interactive_message(
            instance=instance,
            to=to,
            body_text=body_text,
            interactive_type="list",
            list_button_label=content.list_button_label,
            sections=sections_payload,
            session=context.session,
        )
        return Success(output={"to": to, "content_type": "list", "section_count": len(content.sections)})


node_executor_registry.register(SendMessageExecutor())
