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
    # Populated from `modules.admin.models.Plan` via `Business.plan_id`
    # (added in migration 0006 alongside business_template_id) - null
    # when the tenant has no plan assigned. Read-only; a tenant never
    # sets this itself (see plan.py's admin-only assignment endpoint).
    plan_name: str | None = None
    # From `Membership.is_doctor` - the frontend reads this (via whichever
    # of `TokenResponse.businesses`/`MeResponse.memberships` it already
    # has in hand) to gate the clinic-queue module's step-up-auth prompt,
    # with no separate endpoint needed.
    is_doctor: bool = False


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
    """One row of a business's team-members list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    role: MembershipRole
    invited_at: datetime
    accepted_at: datetime | None = None
    # A job-function flag (clinic-queue's doctor designation) - see
    # `Membership.is_doctor`'s own docstring for why it's separate from `role`.
    is_doctor: bool = False


class MemberCreateRequest(BaseModel):
    """Add a new team member to the active business. There is no
    email-invite-link flow in this app (no transactional email sending
    exists anywhere) - the caller (owner/admin) sets the new member's
    password directly and communicates it out-of-band; the account is
    immediately active, no separate acceptance step."""

    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=8, max_length=128)
    role: MembershipRole = MembershipRole.MEMBER
    is_doctor: bool = False


class MemberUpdateRequest(BaseModel):
    """Owner/admin-editable fields on a team member. Currently just the
    doctor flag - `role` editing isn't built yet (still read-only, same as
    before this schema existed)."""

    is_doctor: bool
