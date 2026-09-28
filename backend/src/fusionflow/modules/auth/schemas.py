from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from fusionflow.modules.tenancy.schemas import BusinessMembershipOut


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    business_name: str = Field(min_length=1, max_length=200)
    vertical: str | None = Field(default=None, max_length=80)
    # Starter-kit template chosen at signup, and any extra connectors/modules
    # requested outside that template's bundle - both reviewed together by an
    # admin as one application (see modules.auth.service.signup). Signup no
    # longer issues a session; see SignupResult below.
    business_template_id: uuid.UUID | None = None
    extra_connector_type_keys: list[str] = Field(default_factory=list)


class SignupResult(BaseModel):
    """Returned by `POST /auth/signup` now that self-serve signup requires
    admin approval before login works - no token is issued here."""

    status: str = "pending_approval"
    business_id: uuid.UUID
    business_name: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class SelectBusinessRequest(BaseModel):
    business_id: uuid.UUID


class RefreshRequest(BaseModel):
    """Optional body for non-browser clients.

    Browser clients send nothing: the refresh token travels in the
    httpOnly `fusionflow_refresh` cookie set by the auth router.
    """

    refresh_token: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_platform_admin: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """Result of signup / login / refresh / select-business.

    When `requires_business_selection` is true the access token is an
    *identity-only* pre-tenant token: it carries no `tenant_id`/`role`
    claim and is only good for `GET /auth/me`, `GET /businesses/mine` and
    `POST /auth/select-business`. `businesses` then lists the choices.

    `refresh_token` is also set as an httpOnly+SameSite=Strict cookie; it
    is echoed in the body only as a convenience for non-browser clients
    (mobile/CLI). Browser clients should ignore the body field and let the
    cookie do the work.
    """

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    refresh_token: str | None = None
    requires_business_selection: bool = False
    user: UserOut
    businesses: list[BusinessMembershipOut] = Field(default_factory=list)


class MeResponse(BaseModel):
    user: UserOut
    tenant_id: uuid.UUID | None = None
    role: str | None = None
    platform_admin: bool = False
    memberships: list[BusinessMembershipOut] = Field(default_factory=list)


class StepUpRequest(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class StepUpResponse(BaseModel):
    step_up_token: str
    expires_at: datetime
