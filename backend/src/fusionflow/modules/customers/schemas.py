from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CustomerCreate(BaseModel):
    external_ref: str | None = Field(default=None, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class CustomerUpdate(BaseModel):
    """Partial update — every field optional, unset fields are left alone."""

    external_ref: str | None = Field(default=None, max_length=200)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    email: str | None = Field(default=None, max_length=320)
    phone: str | None = Field(default=None, max_length=40)
    custom_fields: dict[str, Any] | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_ref: str | None = None
    name: str
    email: str | None = None
    phone: str | None = None
    custom_fields: dict[str, Any]
    created_at: datetime
