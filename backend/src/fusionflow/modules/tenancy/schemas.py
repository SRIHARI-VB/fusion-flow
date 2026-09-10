from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.tenancy.models import BusinessStatus, MembershipRole


class BusinessOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    vertical: str | None = None
    status: BusinessStatus
    messaging_paused: bool
    onboarding_completed_at: datetime | None = None
    created_at: datetime


class BusinessMembershipOut(BaseModel):
    """A business as seen by one member - business fields + that user's role."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    vertical: str | None = None
    status: BusinessStatus
    role: MembershipRole
    messaging_paused: bool
    onboarding_completed_at: datetime | None = None


class BusinessUpdateRequest(BaseModel):
    """Owner/admin-editable business profile fields.

    `slug` and `status` are intentionally not editable here: slug changes
    break links, and status is a platform-admin action (M6 suspend /
    reactivate), not a tenant-side one.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    vertical: str | None = Field(default=None, max_length=80)
    mark_onboarding_complete: bool | None = None
    messaging_paused: bool | None = None


class MemberOut(BaseModel):
    """One row of a business's team-members list. Read-only for phase 1."""

    model_config = ConfigDict(from_attributes=True)

    email: str
    role: MembershipRole
    invited_at: datetime
    accepted_at: datetime | None = None
