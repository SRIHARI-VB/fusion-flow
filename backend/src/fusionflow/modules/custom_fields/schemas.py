from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fusionflow.modules.custom_fields.models import EntityType, FieldType

# Lowercase snake_case, must start with a letter - kept deliberately simple
# so a field key is always a safe dict key / eventual column-ish name.
_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"


class FieldDefinitionBase(BaseModel):
    entity_type: EntityType
    key: str = Field(min_length=1, max_length=100, pattern=_KEY_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    field_type: FieldType
    options: list[Any] | None = None
    required: bool = False
    sort_order: int = 0

    @field_validator("options")
    @classmethod
    def _options_required_for_choice_types(cls, value: list[Any] | None, info: Any) -> list[Any] | None:
        field_type = info.data.get("field_type")
        if field_type in (FieldType.SELECT, FieldType.MULTISELECT) and not value:
            raise ValueError("options is required for select/multiselect fields")
        return value


class FieldDefinitionCreate(FieldDefinitionBase):
    pass


class FieldDefinitionUpdate(BaseModel):
    """Partial update. `entity_type`/`key`/`field_type` are immutable after creation -

    changing the shape of an already-applied field is exactly the case the
    plan calls out as needing a migration/backfill tool it explicitly defers
    (Risk #6); deleting and recreating is the phase-1 answer instead.
    """

    label: str | None = Field(default=None, min_length=1, max_length=200)
    options: list[Any] | None = None
    required: bool | None = None
    sort_order: int | None = None


class FieldDefinitionOut(FieldDefinitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_template_id: uuid.UUID | None = None
    created_at: datetime


class FieldTemplateFieldSpec(BaseModel):
    """One entry of `FieldTemplate.fields` - mirrors `FieldDefinitionBase` minus entity_type
    (a template's entity_type is fixed at the template level, not per-field)."""

    key: str = Field(min_length=1, max_length=100, pattern=_KEY_PATTERN)
    label: str = Field(min_length=1, max_length=200)
    field_type: FieldType
    options: list[Any] | None = None
    required: bool = False
    sort_order: int = 0


class FieldTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vertical: str
    entity_type: EntityType
    is_global: bool
    name: str
    version: int
    fields: list[FieldTemplateFieldSpec]
    created_at: datetime


class ApplyTemplateResponse(BaseModel):
    created: list[FieldDefinitionOut]
    skipped_existing_keys: list[str] = Field(default_factory=list)
