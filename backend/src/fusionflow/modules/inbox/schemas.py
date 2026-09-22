"""Unified Inbox DTOs.

`ConversationOut.connector_type_key` is NOT a column - it's populated by
`service.to_conversation_out` joining through `Conversation.
connector_instance.connector_type`, the same "not a plain
`from_attributes` mapping" pattern `connectors/service.py::to_instance_out`
uses for the equivalent field.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_instance_id: uuid.UUID
    connector_type_key: str
    external_contact_id: str
    display_name: str | None = None
    assigned_agent_id: uuid.UUID | None = None
    last_message_at: datetime | None = None
    unread_count: int
    automation_paused: bool
    created_at: datetime
    updated_at: datetime


class SetAutomationPausedRequest(BaseModel):
    paused: bool


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    direction: str
    sender_type: str
    content: str
    external_message_id: str | None = None
    created_at: datetime
    read_at: datetime | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)


class AssignAgentRequest(BaseModel):
    agent_id: uuid.UUID | None = None
