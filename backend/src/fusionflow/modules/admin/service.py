"""Admin domain logic: tenant management, impersonation, feature flags, templates.

Deliberately framework-free where practical (raises `AdminError`, not
`HTTPException`) so `router.py` alone deals with HTTP status mapping,
matching the split `modules/auth/service.py` already uses.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt as pyjwt
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fusionflow.config import get_settings
from fusionflow.core.security import JWT_ALGORITHM
from fusionflow.db.session import set_tenant_context
from fusionflow.modules.admin.models import (
    AuditLog,
    FeatureFlag,
    FeatureFlagOverride,
    ImpersonationSession,
)
from fusionflow.modules.admin.schemas import (
    ConnectorHealthItemOut,
    ConnectorHealthOut,
    FieldTemplateOut,
    FieldTemplatesUnavailableOut,
    TenantMembershipOut,
)
from fusionflow.modules.auth.models import RefreshToken, User
from fusionflow.modules.tenancy.models import Business, BusinessStatus, Membership

settings = get_settings()

# --- Cross-module optional imports -----------------------------------------
# `modules.connectors` (M3/M4, owned by a different Wave-1 agent) and
# `modules.custom_fields` (M2, owned by a different Wave-1 agent) may not
# exist yet in this checkout. Both are guarded so this module can be
# imported - and its own routes can serve everything that doesn't depend on
# them - regardless of which lands first. See the two functions below that
# check these flags.
try:
    from fusionflow.modules.connectors.models import ConnectorInstance  # type: ignore[import-not-found]

    _CONNECTORS_AVAILABLE = True
except ImportError:
    ConnectorInstance = None  # type: ignore[assignment]
    _CONNECTORS_AVAILABLE = False

try:
    from fusionflow.modules.custom_fields.models import FieldTemplate  # type: ignore[import-not-found]

    _FIELD_TEMPLATES_AVAILABLE = True
except ImportError:
    FieldTemplate = None  # type: ignore[assignment]
    _FIELD_TEMPLATES_AVAILABLE = False


class AdminError(Exception):
    def __init__(self, detail: str, status_code: int = 400) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


# --- Tenants -----------------------------------------------------------------


async def list_tenants(session: AsyncSession) -> list[tuple[Business, int]]:
    """Every business plus its accepted-membership count, newest first."""
    rows = await session.execute(
        select(Business, func.count(Membership.id))
        .outerjoin(
            Membership,
            (Membership.business_id == Business.id) & (Membership.accepted_at.is_not(None)),
        )
        .group_by(Business.id)
        .order_by(Business.created_at.desc())
    )
    return [(business, count) for business, count in rows.all()]


async def get_tenant(session: AsyncSession, business_id: uuid.UUID) -> Business | None:
    return await session.get(Business, business_id)


async def get_tenant_memberships(
    session: AsyncSession, business_id: uuid.UUID
) -> list[TenantMembershipOut]:
    rows = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.business_id == business_id)
        .order_by(Membership.invited_at)
    )
    return [
        TenantMembershipOut(
            user_id=user.id,
            email=user.email,
            role=membership.role,
            invited_at=membership.invited_at,
            accepted_at=membership.accepted_at,
        )
        for membership, user in rows.all()
    ]


async def _revoke_refresh_tokens_for_business(session: AsyncSession, business_id: uuid.UUID) -> None:
    """Best-effort session kill on suspend.

    Login/select-business/refresh already refuse a non-ACTIVE business (see
    `modules/auth/service.py` - it filters memberships to
    `BusinessStatus.ACTIVE`), so suspending a tenant blocks new sessions
    immediately. This additionally revokes already-issued refresh tokens for
    that business so a suspended tenant's users cannot silently keep
    refreshing their way to a new access token for up to
    `JWT_REFRESH_TTL_DAYS`. It does *not* invalidate already-issued access
    tokens still inside their (short, `JWT_ACCESS_TTL_MINUTES`) validity
    window - `get_tenant_context` does not re-check `Business.status` on
    every request, only on login/refresh/switch. See this agent's report for
    the note on that residual gap.
    """
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.business_id == business_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


async def suspend_tenant(session: AsyncSession, business_id: uuid.UUID) -> Business:
    business = await get_tenant(session, business_id)
    if business is None:
        raise AdminError("Tenant not found", status_code=404)
    business.status = BusinessStatus.SUSPENDED
    await _revoke_refresh_tokens_for_business(session, business_id)
    await session.flush()
    return business


async def reactivate_tenant(session: AsyncSession, business_id: uuid.UUID) -> Business:
    business = await get_tenant(session, business_id)
    if business is None:
        raise AdminError("Tenant not found", status_code=404)
    business.status = BusinessStatus.ACTIVE
    await session.flush()
    return business


async def get_tenant_connector_health(
    session: AsyncSession, business_id: uuid.UUID
) -> ConnectorHealthOut:
    """One tenant's connector health, as seen by a platform admin.

    Degrades gracefully (`available=False`) if `modules.connectors` hasn't
    landed yet in this checkout - see the guarded import above.

    `ConnectorInstance` is `TenantScopedMixin` (RLS-protected), and this
    admin session does not run under the plan's proposed `BYPASSRLS` admin
    DB role (that role/wiring doesn't exist yet - see this agent's report).
    Since this route is scoped to *one* tenant at a time (not a true
    cross-tenant aggregate list), the correct and sufficient fix is to bind
    this transaction to that one tenant via `SET LOCAL
    app.current_tenant_id` - same mechanism `get_tenant_context` uses for
    ordinary tenant requests - immediately before the query, rather than
    requiring a privileged role.
    """
    if not _CONNECTORS_AVAILABLE:
        return ConnectorHealthOut(
            available=False,
            reason="modules.connectors.ConnectorInstance does not exist in this checkout yet",
        )

    await set_tenant_context(session, business_id)
    rows = (
        (
            await session.execute(
                select(ConnectorInstance)  # type: ignore[arg-type]
                .options(selectinload(ConnectorInstance.connector_type))  # type: ignore[union-attr]
                .where(ConnectorInstance.tenant_id == business_id)  # type: ignore[union-attr]
            )
        )
        .scalars()
        .all()
    )
    return ConnectorHealthOut(
        available=True,
        connectors=[
            ConnectorHealthItemOut(
                id=row.id,
                connector_type_key=row.connector_type.key,
                state=row.state.value,
                last_webhook_at=row.last_webhook_at,
                last_sync_at=row.last_sync_at,
            )
            for row in rows
        ],
    )


# --- Impersonation ------------------------------------------------------------


@dataclass
class ImpersonationResult:
    access_token: str
    expires_in: int
    session_id: uuid.UUID


def _mint_impersonation_token(
    *, target_user_id: uuid.UUID, target_business_id: uuid.UUID, role: str, admin_id: uuid.UUID
) -> tuple[str, str, int]:
    """Mint an access token flagged `impersonated: true` + `acting_admin_id`.

    Deliberately not routed through `core.security.create_access_token` (it
    has no parameter for these two extra claims, and this module avoids
    editing shared `core/` files where a self-contained alternative is
    possible - see this agent's report). The claim *shape* is kept identical
    to `create_access_token`'s (`sub`/`tenant_id`/`role`/`jti`/`platform_admin`
    /`iat`/`exp`) plus the two impersonation-only additions, signed with the
    same secret/algorithm, so every other dependency that decodes access
    tokens (`get_current_user`, `get_tenant_context`, ...) keeps working
    unmodified against an impersonation token.
    """
    now = datetime.now(timezone.utc)
    ttl = timedelta(minutes=settings.JWT_ACCESS_TTL_MINUTES)
    jti = str(uuid.uuid4())
    payload: dict[str, Any] = {
        "sub": str(target_user_id),
        "tenant_id": str(target_business_id),
        "role": role,
        "jti": jti,
        "platform_admin": False,
        "impersonated": True,
        "acting_admin_id": str(admin_id),
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    token = pyjwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, jti, settings.JWT_ACCESS_TTL_MINUTES * 60


async def impersonate(
    session: AsyncSession,
    *,
    admin: User,
    target_user_id: uuid.UUID,
    target_business_id: uuid.UUID,
    reason: str,
) -> ImpersonationResult:
    target_user = await session.get(User, target_user_id)
    if target_user is None:
        raise AdminError("Target user not found", status_code=404)

    business = await get_tenant(session, target_business_id)
    if business is None:
        raise AdminError("Target business not found", status_code=404)
    if business.status != BusinessStatus.ACTIVE:
        raise AdminError("Cannot impersonate into a non-active tenant", status_code=409)

    membership = (
        await session.execute(
            select(Membership).where(
                Membership.user_id == target_user_id,
                Membership.business_id == target_business_id,
                Membership.accepted_at.is_not(None),
            )
        )
    ).scalar_one_or_none()
    if membership is None:
        raise AdminError("Target user is not a member of that business", status_code=404)

    access_token, jti, expires_in = _mint_impersonation_token(
        target_user_id=target_user_id,
        target_business_id=target_business_id,
        role=membership.role.value,
        admin_id=admin.id,
    )

    record = ImpersonationSession(
        id=uuid.uuid4(),
        platform_admin_user_id=admin.id,
        target_user_id=target_user_id,
        target_business_id=target_business_id,
        reason=reason,
        jwt_jti=jti,
    )
    session.add(record)
    await session.flush()

    return ImpersonationResult(access_token=access_token, expires_in=expires_in, session_id=record.id)


# --- Audit log -----------------------------------------------------------------


async def list_audit_log(
    session: AsyncSession,
    *,
    actor_user_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    action: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    filters = []
    if actor_user_id is not None:
        filters.append(AuditLog.actor_user_id == actor_user_id)
    if tenant_id is not None:
        filters.append(AuditLog.tenant_id == tenant_id)
    if action is not None:
        filters.append(AuditLog.action.ilike(f"%{action}%"))
    if since is not None:
        filters.append(AuditLog.created_at >= since)
    if until is not None:
        filters.append(AuditLog.created_at <= until)

    base = select(AuditLog).where(*filters) if filters else select(AuditLog)
    total = (
        await session.execute(
            select(func.count()).select_from(base.order_by(None).subquery())
        )
    ).scalar_one()
    rows = (
        await session.execute(
            base.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    return list(rows), int(total)


# --- Feature flags ---------------------------------------------------------


async def list_feature_flags(session: AsyncSession) -> list[FeatureFlag]:
    return list((await session.execute(select(FeatureFlag).order_by(FeatureFlag.key))).scalars().all())


async def create_feature_flag(
    session: AsyncSession, *, key: str, description: str | None, is_global_default: bool
) -> FeatureFlag:
    existing = (
        await session.execute(select(FeatureFlag).where(FeatureFlag.key == key))
    ).scalar_one_or_none()
    if existing is not None:
        raise AdminError(f"Feature flag '{key}' already exists", status_code=409)
    flag = FeatureFlag(
        id=uuid.uuid4(), key=key, description=description, is_global_default=is_global_default
    )
    session.add(flag)
    await session.flush()
    return flag


async def update_feature_flag(
    session: AsyncSession,
    flag_id: uuid.UUID,
    *,
    description: str | None,
    is_global_default: bool | None,
) -> FeatureFlag:
    flag = await session.get(FeatureFlag, flag_id)
    if flag is None:
        raise AdminError("Feature flag not found", status_code=404)
    if description is not None:
        flag.description = description
    if is_global_default is not None:
        flag.is_global_default = is_global_default
    await session.flush()
    return flag


async def upsert_feature_flag_override(
    session: AsyncSession, flag_id: uuid.UUID, *, tenant_id: uuid.UUID | None, enabled: bool
) -> FeatureFlagOverride:
    flag = await session.get(FeatureFlag, flag_id)
    if flag is None:
        raise AdminError("Feature flag not found", status_code=404)

    existing = (
        await session.execute(
            select(FeatureFlagOverride).where(
                FeatureFlagOverride.feature_flag_id == flag_id,
                FeatureFlagOverride.tenant_id.is_(tenant_id) if tenant_id is None
                else FeatureFlagOverride.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.enabled = enabled
        await session.flush()
        return existing

    override = FeatureFlagOverride(
        id=uuid.uuid4(), feature_flag_id=flag_id, tenant_id=tenant_id, enabled=enabled
    )
    session.add(override)
    await session.flush()
    return override


async def list_feature_flag_overrides(
    session: AsyncSession, flag_id: uuid.UUID
) -> list[FeatureFlagOverride]:
    return list(
        (
            await session.execute(
                select(FeatureFlagOverride).where(FeatureFlagOverride.feature_flag_id == flag_id)
            )
        )
        .scalars()
        .all()
    )


async def is_feature_enabled(
    session: AsyncSession, flag_key: str, tenant_id: uuid.UUID | None
) -> bool:
    """Resolve one flag for one tenant: tenant override > global override > default.

    Exported for other modules to import later (per the plan: "a resolution
    helper function ... that other modules could import later"). Unknown
    flag keys resolve to `False` rather than raising, so callers can gate
    behavior on a flag that doesn't exist yet without special-casing it.
    """
    flag = (
        await session.execute(select(FeatureFlag).where(FeatureFlag.key == flag_key))
    ).scalar_one_or_none()
    if flag is None:
        return False

    if tenant_id is not None:
        tenant_override = (
            await session.execute(
                select(FeatureFlagOverride).where(
                    FeatureFlagOverride.feature_flag_id == flag.id,
                    FeatureFlagOverride.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if tenant_override is not None:
            return tenant_override.enabled

    global_override = (
        await session.execute(
            select(FeatureFlagOverride).where(
                FeatureFlagOverride.feature_flag_id == flag.id,
                FeatureFlagOverride.tenant_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if global_override is not None:
        return global_override.enabled

    return flag.is_global_default


# --- Global field templates --------------------------------------------------


async def list_field_templates(
    session: AsyncSession,
) -> list[FieldTemplateOut] | FieldTemplatesUnavailableOut:
    """Read-only for now: global template *authoring* is left to a follow-up
    since this agent does not own `modules.custom_fields`'s schema - see this
    agent's report. Still degrades to `FieldTemplatesUnavailableOut` for a
    checkout where that module hasn't landed at all.
    """
    if not _FIELD_TEMPLATES_AVAILABLE:
        return FieldTemplatesUnavailableOut()

    rows = (
        (await session.execute(select(FieldTemplate).order_by(FieldTemplate.vertical)))  # type: ignore[arg-type]
        .scalars()
        .all()
    )
    return [
        FieldTemplateOut(
            id=row.id,
            vertical=row.vertical,
            entity_type=row.entity_type.value,
            name=row.name,
            version=row.version,
            is_global=row.is_global,
            field_count=len(row.fields or []),
        )
        for row in rows
    ]


def field_templates_available() -> bool:
    return _FIELD_TEMPLATES_AVAILABLE


# --- Billing usage (stub) ----------------------------------------------------


async def get_billing_usage_stub(session: AsyncSession) -> dict[str, Any]:
    tenants_count = int(
        (await session.execute(select(func.count()).select_from(Business))).scalar_one()
    )
    return {
        "available": False,
        "reason": "Billing/usage metering is not implemented yet (Phase 2+ per the plan)",
        "tenants_count": tenants_count,
    }
