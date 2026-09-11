from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from fusionflow.modules.custom_fields.models import FieldType

# Lowercase snake_case, must start with a letter - same convention as
# `custom_fields.schemas._KEY_PATTERN`, so both an object type's `key` and
# its fields' `key`s are always safe module-picker/dict keys.
_KEY_PATTERN = r"^[a-z][a-z0-9_]*$"


# ---------------------------------------------------------------------------
# ObjectTypeDefinition
# ---------------------------------------------------------------------------


class ObjectTypeCreate(BaseModel):
    key: str = Field(min_length=1, max_length=80, pattern=_KEY_PATTERN)
    name: str = Field(min_length=1, max_length=200)
    icon: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class ObjectTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    icon: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class ObjectTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    name: str
    icon: str | None
    description: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# ObjectFieldDefinition
# ---------------------------------------------------------------------------


class ObjectFieldDefinitionBase(BaseModel):
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


class ObjectFieldDefinitionCreate(ObjectFieldDefinitionBase):
    pass


class ObjectFieldDefinitionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    options: list[Any] | None = None
    required: bool | None = None
    sort_order: int | None = None


class ObjectFieldDefinitionOut(ObjectFieldDefinitionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    object_type_id: uuid.UUID
    created_at: datetime


# ---------------------------------------------------------------------------
# ObjectRecord
# ---------------------------------------------------------------------------


class ObjectRecordCreate(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    customer_id: uuid.UUID | None = None


class ObjectRecordUpdate(BaseModel):
    """Partial update - `payload` is merged into the existing payload (not
    replaced) before re-validation. See `service.update_record`."""

    payload: dict[str, Any] | None = None
    customer_id: uuid.UUID | None = None


class ObjectRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    object_type_id: uuid.UUID
    payload: dict[str, Any]
    customer_id: uuid.UUID | None
    created_by_run_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
