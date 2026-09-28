"""Connector framework DTOs.

Hard rule enforced here by construction: no schema in this module ever
references `ConnectorCredential` or any of its fields. Secrets flow
in via `ConnectRequest.params` (validated/consumed by the adapter, never
echoed back) and never flow out at all - `ConnectorInstanceOut` only ever
carries the adapter-populated `connected_identity` allowlist.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fusionflow.modules.connectors.models import (
    ConnectorAccessRequestStatus,
    ConnectorCategory,
    ConnectorEventType,
    ConnectorState,
    HealthStatus,
)
from fusionflow.modules.tenancy.models import MembershipRole


class ConnectorTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    key: str
    category: ConnectorCategory
    display_name: str
    config_schema: dict[str, Any]
    oauth: bool
    is_enabled_globally: bool
    # One of "granted" (in the tenant's business_template bundle, or an
    # approved access request), "pending" (access request awaiting admin
    # review), "denied", "restricted" (tenant has it, but an Owner/Admin
    # blocked the CALLER's role from it), or "not_requested". Computed
    # per-tenant-and-role by `service.get_connector_access_map_for_role` -
    # never `from_attributes`'d straight off the ORM row, see
    # `service.to_type_out`.
    access_status: str = "granted"
    # Static, tenant-independent webhook setup instructions (see
    # `base.ConnectorAdapter.webhook_setup_hint`) - null for a provider
    # that doesn't need a manual webhook configuration step.
    webhook_callback_url: str | None = None
    webhook_verify_token: str | None = None


class ConnectorInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_type_id: uuid.UUID
    connector_type_key: str
    connector_type_display_name: str
    connector_category: ConnectorCategory
    state: ConnectorState
    display_name: str
    connected_identity: dict[str, Any] | None = None
    health_status: HealthStatus | None = None
    last_webhook_at: datetime | None = None
    last_sync_at: datetime | None = None
    last_error_message: str | None = None
    provider_ref_ids: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    disconnected_at: datetime | None = None


class ConnectorEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_instance_id: uuid.UUID
    event_type: ConnectorEventType
    payload: dict[str, Any]
    occurred_at: datetime


class ConnectRequest(BaseModel):
    """Generic connect payload.

    `params` is intentionally an untyped bag: an api_key adapter (e.g.
    Razorpay) reads `key_id`/`key_secret`/`webhook_secret` out of it; an
    oauth adapter (e.g. WhatsApp) typically ignores it (the real secret
    exchange happens in the OAuth callback) but may use it to carry a
    display name or an Embedded-Signup-supplied `code`. Each adapter
    validates its own `params` against `config_schema` - `router.py`
    never inspects the contents.
    """

    display_name: str | None = Field(default=None, max_length=200)
    params: dict[str, Any] = Field(default_factory=dict)


class ConnectResponse(BaseModel):
    instance: ConnectorInstanceOut
    redirect_url: str | None = None


class MediaUploadOut(BaseModel):
    """`POST /connectors/{instance_id}/media`'s response - the uploaded
    object's (provider-hosted) URL."""

    url: str


class ConnectorAccessRequestCreate(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class ConnectorAccessRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    connector_type_id: uuid.UUID
    connector_type_key: str
    status: ConnectorAccessRequestStatus
    reason: str | None = None
    requested_by: uuid.UUID
    reviewed_by: uuid.UUID | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


class ModuleRoleAccessOut(BaseModel):
    connector_type_id: uuid.UUID
    key: str
    display_name: str
    member_restricted: bool
    viewer_restricted: bool


class SetRoleRestrictionRequest(BaseModel):
    connector_type_id: uuid.UUID
    role: MembershipRole
    restricted: bool
