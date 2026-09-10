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
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fusionflow.config import get_settings
from fusionflow.core.security import JWT_ALGORITHM
from fusionflow.db.session import set_tenant_context, unscoped_session_factory
from fusionflow.modules.admin.models import (
    AuditLog,
    BusinessTemplate,
    BusinessTemplateConnectorType,
    FeatureFlag,
    FeatureFlagOverride,
    ImpersonationSession,
    Plan,
    PlanFeatureFlag,
    PlanResourceLimit,
    ResourceLimitOverride,
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
    from fusionflow.modules.connectors import service as connector_service  # type: ignore[import-not-found]
    from fusionflow.modules.connectors.models import (  # type: ignore[import-not-found]
        ConnectorAccessOverride,
        ConnectorAccessRequest,
        ConnectorAccessRequestStatus,
        ConnectorInstance,
        ConnectorType,
    )

    _CONNECTORS_AVAILABLE = True
except ImportError:
    connector_service = None  # type: ignore[assignment]
    ConnectorAccessOverride = None  # type: ignore[assignment]
    ConnectorAccessRequest = None  # type: ignore[assignment]
    ConnectorAccessRequestStatus = None  # type: ignore[assignment]
    ConnectorInstance = None  # type: ignore[assignment]
    ConnectorType = None  # type: ignore[assignment]
    _CONNECTORS_AVAILABLE = False

try:
    from fusionflow.modules.custom_fields.models import FieldTemplate  # type: ignore[import-not-found]
    from fusionflow.modules.custom_fields import service as custom_fields_service  # type: ignore[import-not-found]

    _FIELD_TEMPLATES_AVAILABLE = True
except ImportError:
    FieldTemplate = None  # type: ignore[assignment]
    custom_fields_service = None  # type: ignore[assignment]
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


async def _apply_field_templates_for_vertical(session: AsyncSession, business: Business) -> None:
    """Server-side equivalent of the tenant-initiated
    `listFieldTemplates({vertical}) -> applyFieldTemplate(id)` sequence
    `OnboardingPage.tsx` used to run - moved here because the tenant has no
    session to make those calls with until admin approval grants one.
    Best-effort: degrades to a no-op if `modules.custom_fields` isn't
    available in this checkout (same guard this module already uses
    elsewhere), or if the business has no vertical set.
    """
    if not _FIELD_TEMPLATES_AVAILABLE or business.vertical is None:
        return
    await set_tenant_context(session, business.id)
    templates = await custom_fields_service.list_templates(  # type: ignore[union-attr]
        session, vertical=business.vertical, entity_type=None
    )
    for template in templates:
        await custom_fields_service.apply_template(  # type: ignore[union-attr]
            session, tenant_id=business.id, template=template
        )


async def approve_tenant(session: AsyncSession, business_id: uuid.UUID, *, admin_id: uuid.UUID) -> Business:
    """`PENDING_APPROVAL -> ACTIVE`. Does NOT auto-approve the tenant's own
    pending `ConnectorAccessRequest` rows from signup - those stay in the
    normal `/admin/connector-access-requests` queue for independent review,
    the same unified mechanism used for any post-onboarding request."""
    business = await get_tenant(session, business_id)
    if business is None:
        raise AdminError("Tenant not found", status_code=404)
    if business.status != BusinessStatus.PENDING_APPROVAL:
        raise AdminError("Only a pending application can be approved", status_code=409)
    business.status = BusinessStatus.ACTIVE
    business.denial_reason = None
    business.reviewed_by = admin_id
    business.reviewed_at = datetime.now(timezone.utc)
    if business.business_template_id is not None:
        await _apply_field_templates_for_vertical(session, business)
    await session.flush()
    return business


async def deny_tenant(
    session: AsyncSession, business_id: uuid.UUID, *, admin_id: uuid.UUID, reason: str | None
) -> Business:
    """`PENDING_APPROVAL -> DENIED`, with an optional reason shown to the
    applicant at their next login attempt."""
    business = await get_tenant(session, business_id)
    if business is None:
        raise AdminError("Tenant not found", status_code=404)
    if business.status != BusinessStatus.PENDING_APPROVAL:
        raise AdminError("Only a pending application can be denied", status_code=409)
    business.status = BusinessStatus.DENIED
    business.denial_reason = reason
    business.reviewed_by = admin_id
    business.reviewed_at = datetime.now(timezone.utc)
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


# --- Per-tenant module/connector access overrides (revoke/grant) -------------
#
# Closes a real gap: there was no way to revoke a single connector/module
# from one tenant without either reassigning its whole business_template
# (changing every other grant it gives) or unassigning it entirely - which,
# for FEATURE-category modules, actually *over*-grants via the
# grandfathering compat branch in `modules.connectors.deps`. See
# `modules.connectors.models.ConnectorAccessOverride`'s docstring.


async def get_tenant_module_access(session: AsyncSession, business_id: uuid.UUID) -> list[dict[str, Any]]:
    """Full connector/module catalog + this tenant's resolved `access_status`
    + whether an admin override exists, for the admin's per-tenant "Modules
    & connectors" panel. Same `set_tenant_context`-on-the-request-session
    pattern as `get_tenant_connector_health` above - no `app.current_tenant_id`
    is set by default under `/api/admin/*`."""
    if not _CONNECTORS_AVAILABLE:
        return []

    await set_tenant_context(session, business_id)
    types = await connector_service.list_connector_types(session)
    access_map = await connector_service.get_connector_access_map(
        session, tenant_id=business_id, connector_type_ids=[t.id for t in types]
    )
    overrides = await connector_service.get_connector_access_overrides(session, tenant_id=business_id)
    return [
        {
            "connector_type_id": t.id,
            "connector_type_key": t.key,
            "display_name": t.display_name,
            "category": t.category.value,
            "access_status": access_map.get(t.id, "not_requested"),
            "has_override": t.id in overrides,
            "override_granted": overrides[t.id].granted if t.id in overrides else None,
        }
        for t in types
    ]


async def set_connector_access_override(
    session: AsyncSession,
    business_id: uuid.UUID,
    type_key: str,
    *,
    granted: bool,
    admin_id: uuid.UUID,
    reason: str | None,
) -> "ConnectorAccessOverride":
    if not _CONNECTORS_AVAILABLE:
        raise AdminError("modules.connectors is not available in this checkout", status_code=501)

    await set_tenant_context(session, business_id)
    connector_type = await connector_service.get_connector_type_by_key(session, type_key)
    if connector_type is None:
        raise AdminError(f"Unknown connector type: {type_key!r}", status_code=404)

    existing = (
        await session.execute(
            select(ConnectorAccessOverride).where(  # type: ignore[arg-type]
                ConnectorAccessOverride.tenant_id == business_id,  # type: ignore[union-attr]
                ConnectorAccessOverride.connector_type_id == connector_type.id,  # type: ignore[union-attr]
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.granted = granted
        existing.set_by = admin_id
        existing.reason = reason
        await session.flush()
        return existing

    override = ConnectorAccessOverride(
        id=uuid.uuid4(),
        tenant_id=business_id,
        connector_type_id=connector_type.id,
        granted=granted,
        set_by=admin_id,
        reason=reason,
    )
    session.add(override)
    await session.flush()
    return override


async def clear_connector_access_override(session: AsyncSession, business_id: uuid.UUID, type_key: str) -> None:
    """Deletes the override, reverting resolution to the normal
    bundle/request/grandfather chain in `get_connector_access_map`."""
    if not _CONNECTORS_AVAILABLE:
        raise AdminError("modules.connectors is not available in this checkout", status_code=501)

    await set_tenant_context(session, business_id)
    connector_type = await connector_service.get_connector_type_by_key(session, type_key)
    if connector_type is None:
        raise AdminError(f"Unknown connector type: {type_key!r}", status_code=404)

    await session.execute(
        delete(ConnectorAccessOverride).where(  # type: ignore[arg-type]
            ConnectorAccessOverride.tenant_id == business_id,  # type: ignore[union-attr]
            ConnectorAccessOverride.connector_type_id == connector_type.id,  # type: ignore[union-attr]
        )
    )
    await session.flush()


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

# The catalog an admin actually needs when creating a flag: a `key` only
# matters if some code path calls `is_feature_enabled(session, key, ...)`
# with that exact string - before this catalog existed, an admin had to
# already know (or go find in the codebase) the precise key a developer
# picked, typed freely into a text box with no validation against typos.
# `gates_real_behavior` is honest about which of these actually flip
# something today (`support_agent_enabled` gates the /support-agent nav
# item + route - see modules.tenancy.router::my_feature_flags and
# frontend/web/src/App.tsx) versus ones reserved for a Phase 2+ feature
# that doesn't exist yet (toggling them is a no-op until that code lands,
# same "resolves False for an unknown flag" safety the resolver already
# has - these three just also happen to be *known* unknowns).
KNOWN_FEATURE_FLAGS: list[dict[str, str | bool]] = [
    {
        "key": "support_agent_enabled",
        "label": "Support Agent (BYOM AI)",
        "description": "Shows the Support Agent nav item and unlocks /support-agent for this tenant.",
        "gates_real_behavior": True,
    },
    {
        "key": "advanced_workflows",
        "label": "Advanced workflow features",
        "description": "Reserved for a Phase 2+ workflow node/condition library expansion - not wired to any behavior yet.",
        "gates_real_behavior": False,
    },
    {
        "key": "dashboard_customization",
        "label": "Dashboard customization",
        "description": "Reserved for the Phase 2+ dashboard widget framework - not wired to any behavior yet.",
        "gates_real_behavior": False,
    },
]


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
    """Resolve one flag for one tenant.

    Resolution order: tenant override > tenant's plan entitlement >
    global override > flag default. The plan tier was added for the
    "business templates, connector access requests, and plan entitlements"
    feature - see `modules.admin.models.Plan`/`PlanFeatureFlag`.

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

        # Plan tier: `getattr(..., None)` rather than `business.plan_id`
        # directly is defensive, not because the column is missing (it
        # landed in migration 0006) - a tenant simply may not have a plan
        # assigned, which is exactly "no plan" too.
        business = await session.get(Business, tenant_id)
        plan_id = getattr(business, "plan_id", None) if business is not None else None
        if plan_id is not None:
            plan_flag = (
                await session.execute(
                    select(PlanFeatureFlag).where(
                        PlanFeatureFlag.plan_id == plan_id,
                        PlanFeatureFlag.feature_flag_id == flag.id,
                    )
                )
            ).scalar_one_or_none()
            if plan_flag is not None:
                return plan_flag.enabled

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


async def get_resource_limit(
    session: AsyncSession, *, tenant_id: uuid.UUID, resource_key: str
) -> int | None:
    """Resolve the max-row-count ceiling for one tenant on one resource
    (e.g. "products", "kb"), or `None` for unlimited.

    Resolution order: tenant override (`ResourceLimitOverride`) > tenant's
    plan (`PlanResourceLimit`) > unlimited - the same shape as
    `is_feature_enabled` above, minus the global-override tier (a resource
    limit is either set for a plan/tenant or it doesn't exist - there is no
    "everyone gets N by default" concept the way `FeatureFlag.is_global_default`
    is for booleans). Keyed by the same `connector_types.key` catalog
    `require_module_access` already gates modules by - unknown keys resolve
    to unlimited rather than raising, matching `is_feature_enabled`'s
    "unknown key -> permissive default" convention... except here
    "permissive" means unlimited, not `False`.
    """
    if not _CONNECTORS_AVAILABLE:
        return None

    connector_type = await connector_service.get_connector_type_by_key(session, resource_key)
    if connector_type is None:
        return None

    tenant_override = (
        await session.execute(
            select(ResourceLimitOverride).where(
                ResourceLimitOverride.tenant_id == tenant_id,
                ResourceLimitOverride.connector_type_id == connector_type.id,
            )
        )
    ).scalar_one_or_none()
    if tenant_override is not None:
        return tenant_override.max_count

    business = await session.get(Business, tenant_id)
    plan_id = business.plan_id if business is not None else None
    if plan_id is not None:
        plan_limit = (
            await session.execute(
                select(PlanResourceLimit).where(
                    PlanResourceLimit.plan_id == plan_id,
                    PlanResourceLimit.connector_type_id == connector_type.id,
                )
            )
        ).scalar_one_or_none()
        if plan_limit is not None:
            return plan_limit.max_count

    return None


async def resolve_known_flags_for_tenant(
    session: AsyncSession, tenant_id: uuid.UUID
) -> dict[str, bool]:
    """`{flag_key: enabled}` for every entry in `KNOWN_FEATURE_FLAGS`, for one tenant.

    Backs the tenant-facing `GET /businesses/mine/feature-flags` (see
    `modules.tenancy.router`) - the web app calls this once to decide
    what to show (e.g. the Support Agent nav item), rather than each
    frontend feature needing its own bespoke gating logic. A flag that
    doesn't exist yet in the `feature_flags` table (nobody has created it
    in the admin panel yet) resolves to `False` via the same
    unknown-key-is-safe behavior `is_feature_enabled` already has.
    """
    return {
        str(entry["key"]): await is_feature_enabled(session, str(entry["key"]), tenant_id)
        for entry in KNOWN_FEATURE_FLAGS
    }


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


# --- Plans -------------------------------------------------------------------


async def list_plans(session: AsyncSession) -> list[Plan]:
    return list((await session.execute(select(Plan).order_by(Plan.name))).scalars().all())


async def get_plan(session: AsyncSession, plan_id: uuid.UUID) -> Plan | None:
    return await session.get(Plan, plan_id)


async def create_plan(session: AsyncSession, *, key: str, name: str, is_default: bool) -> Plan:
    existing = (await session.execute(select(Plan).where(Plan.key == key))).scalar_one_or_none()
    if existing is not None:
        raise AdminError(f"Plan '{key}' already exists", status_code=409)
    if is_default:
        # Only one plan can be the default at a time - clear any existing one.
        await session.execute(update(Plan).values(is_default=False))
    plan = Plan(id=uuid.uuid4(), key=key, name=name, is_default=is_default)
    session.add(plan)
    await session.flush()
    return plan


async def update_plan(
    session: AsyncSession, plan_id: uuid.UUID, *, name: str | None, is_default: bool | None
) -> Plan:
    plan = await get_plan(session, plan_id)
    if plan is None:
        raise AdminError("Plan not found", status_code=404)
    if name is not None:
        plan.name = name
    if is_default is not None:
        if is_default:
            await session.execute(update(Plan).values(is_default=False))
        plan.is_default = is_default
    await session.flush()
    return plan


async def list_plan_feature_flags(session: AsyncSession, plan_id: uuid.UUID) -> list[PlanFeatureFlag]:
    return list(
        (
            await session.execute(select(PlanFeatureFlag).where(PlanFeatureFlag.plan_id == plan_id))
        )
        .scalars()
        .all()
    )


async def set_plan_feature_flags(
    session: AsyncSession, plan_id: uuid.UUID, *, flags: list[tuple[uuid.UUID, bool]]
) -> list[PlanFeatureFlag]:
    """Upserts each `(feature_flag_id, enabled)` pair for this plan.

    Replace-by-key, not replace-all: flags not named in `flags` keep
    whatever entitlement they already had for this plan (mirrors
    `upsert_feature_flag_override`'s upsert-not-replace convention).
    """
    plan = await get_plan(session, plan_id)
    if plan is None:
        raise AdminError("Plan not found", status_code=404)

    result: list[PlanFeatureFlag] = []
    for feature_flag_id, enabled in flags:
        flag = await session.get(FeatureFlag, feature_flag_id)
        if flag is None:
            raise AdminError(f"Feature flag {feature_flag_id} not found", status_code=404)
        existing = (
            await session.execute(
                select(PlanFeatureFlag).where(
                    PlanFeatureFlag.plan_id == plan_id,
                    PlanFeatureFlag.feature_flag_id == feature_flag_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.enabled = enabled
            result.append(existing)
        else:
            row = PlanFeatureFlag(
                id=uuid.uuid4(), plan_id=plan_id, feature_flag_id=feature_flag_id, enabled=enabled
            )
            session.add(row)
            result.append(row)
    await session.flush()
    return result


async def assign_tenant_plan(
    session: AsyncSession, business_id: uuid.UUID, *, plan_id: uuid.UUID | None
) -> Business:
    """`plan_id=None` unassigns. `Business.plan_id` doesn't exist on the ORM
    model in this checkout yet - see this task's report; the assignment
    below is a documented no-op until that column lands via migration."""
    business = await get_tenant(session, business_id)
    if business is None:
        raise AdminError("Tenant not found", status_code=404)
    if plan_id is not None:
        plan = await get_plan(session, plan_id)
        if plan is None:
            raise AdminError("Plan not found", status_code=404)
    business.plan_id = plan_id  # type: ignore[attr-defined]
    await session.flush()
    return business


# --- Resource count limits (plan defaults + tenant overrides) ----------------
#
# Mirrors the plan_feature_flags/feature_flag_overrides shape one section
# up, applied to counts instead of booleans - see `get_resource_limit`'s
# docstring for the resolution order this powers.


async def list_plan_resource_limits(session: AsyncSession, plan_id: uuid.UUID) -> list[PlanResourceLimit]:
    return list(
        (
            await session.execute(select(PlanResourceLimit).where(PlanResourceLimit.plan_id == plan_id))
        )
        .scalars()
        .all()
    )


async def set_plan_resource_limits(
    session: AsyncSession, plan_id: uuid.UUID, *, limits: list[tuple[str, int | None]]
) -> list[PlanResourceLimit]:
    """Upserts each `(resource_key, max_count)` pair for this plan.
    `max_count=None` deletes the row for that key (reverts to unlimited at
    the plan level) rather than storing a sentinel - matches how "no row"
    already means unlimited in `get_resource_limit`."""
    if not _CONNECTORS_AVAILABLE:
        raise AdminError("modules.connectors is not available in this checkout", status_code=501)

    plan = await get_plan(session, plan_id)
    if plan is None:
        raise AdminError("Plan not found", status_code=404)

    result: list[PlanResourceLimit] = []
    for resource_key, max_count in limits:
        connector_type = await connector_service.get_connector_type_by_key(session, resource_key)
        if connector_type is None:
            raise AdminError(f"Unknown resource key: {resource_key!r}", status_code=404)
        existing = (
            await session.execute(
                select(PlanResourceLimit).where(
                    PlanResourceLimit.plan_id == plan_id,
                    PlanResourceLimit.connector_type_id == connector_type.id,
                )
            )
        ).scalar_one_or_none()
        if max_count is None:
            if existing is not None:
                await session.delete(existing)
            continue
        if existing is not None:
            existing.max_count = max_count
            result.append(existing)
        else:
            row = PlanResourceLimit(
                id=uuid.uuid4(), plan_id=plan_id, connector_type_id=connector_type.id, max_count=max_count
            )
            session.add(row)
            result.append(row)
    await session.flush()
    return result


async def get_tenant_resource_limits(session: AsyncSession, business_id: uuid.UUID) -> list[dict[str, Any]]:
    """Every resource key's effective limit + source + current usage, for
    the admin's per-tenant resource-limits panel."""
    if not _CONNECTORS_AVAILABLE:
        return []

    await set_tenant_context(session, business_id)
    types = await connector_service.list_connector_types(session)
    overrides = {
        o.connector_type_id: o
        for o in (
            await session.execute(
                select(ResourceLimitOverride).where(ResourceLimitOverride.tenant_id == business_id)
            )
        )
        .scalars()
        .all()
    }
    business = await session.get(Business, business_id)
    plan_id = business.plan_id if business is not None else None
    plan_limits: dict[uuid.UUID, int] = {}
    if plan_id is not None:
        plan_limits = {
            row.connector_type_id: row.max_count
            for row in (
                await session.execute(
                    select(PlanResourceLimit).where(PlanResourceLimit.plan_id == plan_id)
                )
            )
            .scalars()
            .all()
        }

    result = []
    for t in types:
        override = overrides.get(t.id)
        if override is not None:
            limit, source = override.max_count, "tenant_override"
        elif t.id in plan_limits:
            limit, source = plan_limits[t.id], "plan"
        else:
            limit, source = None, "unlimited"
        result.append(
            {
                "connector_type_id": t.id,
                "connector_type_key": t.key,
                "display_name": t.display_name,
                "limit": limit,
                "source": source,
            }
        )
    return result


async def set_resource_limit_override(
    session: AsyncSession, business_id: uuid.UUID, resource_key: str, *, max_count: int
) -> ResourceLimitOverride:
    if not _CONNECTORS_AVAILABLE:
        raise AdminError("modules.connectors is not available in this checkout", status_code=501)

    await set_tenant_context(session, business_id)
    connector_type = await connector_service.get_connector_type_by_key(session, resource_key)
    if connector_type is None:
        raise AdminError(f"Unknown resource key: {resource_key!r}", status_code=404)

    existing = (
        await session.execute(
            select(ResourceLimitOverride).where(
                ResourceLimitOverride.tenant_id == business_id,
                ResourceLimitOverride.connector_type_id == connector_type.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        existing.max_count = max_count
        await session.flush()
        return existing

    override = ResourceLimitOverride(
        id=uuid.uuid4(), tenant_id=business_id, connector_type_id=connector_type.id, max_count=max_count
    )
    session.add(override)
    await session.flush()
    return override


async def clear_resource_limit_override(session: AsyncSession, business_id: uuid.UUID, resource_key: str) -> None:
    if not _CONNECTORS_AVAILABLE:
        raise AdminError("modules.connectors is not available in this checkout", status_code=501)

    await set_tenant_context(session, business_id)
    connector_type = await connector_service.get_connector_type_by_key(session, resource_key)
    if connector_type is None:
        raise AdminError(f"Unknown resource key: {resource_key!r}", status_code=404)

    await session.execute(
        delete(ResourceLimitOverride).where(
            ResourceLimitOverride.tenant_id == business_id,
            ResourceLimitOverride.connector_type_id == connector_type.id,
        )
    )
    await session.flush()


# --- Business templates -------------------------------------------------------


async def list_business_templates(session: AsyncSession) -> list[BusinessTemplate]:
    return list(
        (await session.execute(select(BusinessTemplate).order_by(BusinessTemplate.name))).scalars().all()
    )


async def get_business_template(session: AsyncSession, template_id: uuid.UUID) -> BusinessTemplate | None:
    return await session.get(BusinessTemplate, template_id)


async def get_business_template_connector_type_ids(
    session: AsyncSession, template_id: uuid.UUID
) -> list[uuid.UUID]:
    rows = await session.execute(
        select(BusinessTemplateConnectorType.connector_type_id).where(
            BusinessTemplateConnectorType.business_template_id == template_id
        )
    )
    return list(rows.scalars().all())


async def _replace_business_template_connector_types(
    session: AsyncSession, template_id: uuid.UUID, connector_type_ids: list[uuid.UUID]
) -> None:
    await session.execute(
        delete(BusinessTemplateConnectorType).where(
            BusinessTemplateConnectorType.business_template_id == template_id
        )
    )
    for connector_type_id in connector_type_ids:
        session.add(
            BusinessTemplateConnectorType(
                id=uuid.uuid4(),
                business_template_id=template_id,
                connector_type_id=connector_type_id,
            )
        )
    await session.flush()


async def create_business_template(
    session: AsyncSession,
    *,
    key: str,
    name: str,
    description: str | None,
    vertical: str | None,
    plan_id: uuid.UUID | None,
    is_active: bool,
    connector_type_ids: list[uuid.UUID],
) -> BusinessTemplate:
    existing = (
        await session.execute(select(BusinessTemplate).where(BusinessTemplate.key == key))
    ).scalar_one_or_none()
    if existing is not None:
        raise AdminError(f"Business template '{key}' already exists", status_code=409)

    template = BusinessTemplate(
        id=uuid.uuid4(),
        key=key,
        name=name,
        description=description,
        vertical=vertical,
        plan_id=plan_id,
        is_active=is_active,
    )
    session.add(template)
    await session.flush()
    if connector_type_ids:
        await _replace_business_template_connector_types(session, template.id, connector_type_ids)
    return template


async def update_business_template(
    session: AsyncSession,
    template_id: uuid.UUID,
    *,
    name: str | None,
    description: str | None,
    vertical: str | None,
    plan_id: uuid.UUID | None,
    is_active: bool | None,
    connector_type_ids: list[uuid.UUID] | None,
) -> BusinessTemplate:
    template = await get_business_template(session, template_id)
    if template is None:
        raise AdminError("Business template not found", status_code=404)
    if name is not None:
        template.name = name
    if description is not None:
        template.description = description
    if vertical is not None:
        template.vertical = vertical
    if plan_id is not None:
        template.plan_id = plan_id
    if is_active is not None:
        template.is_active = is_active
    await session.flush()
    if connector_type_ids is not None:
        await _replace_business_template_connector_types(session, template.id, connector_type_ids)
    return template


# --- Connector access requests (cross-tenant admin queue) --------------------


def connectors_available() -> bool:
    return _CONNECTORS_AVAILABLE


async def list_connector_type_catalog(session: AsyncSession) -> list[dict[str, Any]]:
    """Minimal `connector_types` projection for the admin "pick connectors for
    this business-template bundle" UI - `/api/admin/*` has no tenant context
    (see this module's module docstring), so it can't reuse
    `modules.connectors.router.list_connector_types` (which computes a
    per-tenant `access_status`); this is the global catalog only, no
    per-tenant fields at all."""
    if not _CONNECTORS_AVAILABLE:
        return []
    rows = (
        await session.execute(select(ConnectorType).order_by(ConnectorType.display_name))  # type: ignore[arg-type]
    ).scalars().all()
    return [
        {"id": row.id, "key": row.key, "display_name": row.display_name, "category": row.category.value}
        for row in rows
    ]


async def list_connector_access_requests(*, status_filter: str | None = None) -> list[dict[str, Any]]:
    """The cross-tenant "pending connector access requests" admin queue.

    A true cross-tenant read RLS can never satisfy (see
    `fusionflow.db.session.unscoped_session_factory`'s docstring) - runs on
    that unscoped session for this one read, then discards it. Never mixed
    with a mutation (approve/deny go through `_review_connector_access_request`,
    which re-derives tenant context from scratch on a normal session).
    """
    if not _CONNECTORS_AVAILABLE:
        return []

    async with unscoped_session_factory() as session:
        query = (
            select(ConnectorAccessRequest, Business, ConnectorType, User)  # type: ignore[arg-type]
            .join(Business, Business.id == ConnectorAccessRequest.tenant_id)  # type: ignore[union-attr]
            .join(ConnectorType, ConnectorType.id == ConnectorAccessRequest.connector_type_id)  # type: ignore[union-attr]
            .join(User, User.id == ConnectorAccessRequest.requested_by)  # type: ignore[union-attr]
        )
        if status_filter is not None:
            query = query.where(
                ConnectorAccessRequest.status == ConnectorAccessRequestStatus(status_filter)  # type: ignore[union-attr]
            )
        rows = (await session.execute(query)).all()

    def _sort_key(row: tuple[Any, ...]) -> tuple[int, float]:
        request = row[0]
        pending_first = 0 if request.status == ConnectorAccessRequestStatus.PENDING else 1
        return (pending_first, -request.created_at.timestamp())

    rows = sorted(rows, key=_sort_key)
    return [
        {
            "id": request.id,
            "tenant_id": request.tenant_id,
            "business_name": business.name,
            "business_status": business.status.value,
            "connector_type_id": request.connector_type_id,
            "connector_type_key": connector_type.key,
            "status": request.status.value,
            "reason": request.reason,
            "requested_by": request.requested_by,
            "requested_by_email": user.email,
            "reviewed_by": request.reviewed_by,
            "reviewed_at": request.reviewed_at,
            "created_at": request.created_at,
        }
        for request, business, connector_type, user in rows
    ]


async def _resolve_access_request_tenant(request_id: uuid.UUID) -> uuid.UUID | None:
    """Learn which tenant a `request_id` belongs to, bypassing RLS.

    Same chicken-and-egg problem as `connectors.service._resolve_oauth_state_tenant`:
    an admin request has no `app.current_tenant_id` set, and a plain RLS-scoped
    read of this tenant-scoped row returns nothing even though it exists. Used
    ONLY to learn the tenant_id; the authoritative fetch+mutate happens
    afterward on the normal session, once `set_tenant_context` has run.
    """
    if not _CONNECTORS_AVAILABLE:
        return None
    async with unscoped_session_factory() as session:
        request = await session.get(ConnectorAccessRequest, request_id)  # type: ignore[arg-type]
        return request.tenant_id if request is not None else None


async def _review_connector_access_request(
    session: AsyncSession, request_id: uuid.UUID, *, admin_id: uuid.UUID, approve: bool
) -> ConnectorAccessRequest:
    if not _CONNECTORS_AVAILABLE:
        raise AdminError("modules.connectors is not available in this checkout", status_code=501)

    tenant_id = await _resolve_access_request_tenant(request_id)
    if tenant_id is None:
        raise AdminError("Connector access request not found", status_code=404)
    await set_tenant_context(session, tenant_id)

    request = await session.get(ConnectorAccessRequest, request_id)  # type: ignore[arg-type]
    if request is None:
        raise AdminError("Connector access request not found", status_code=404)
    if request.status != ConnectorAccessRequestStatus.PENDING:
        raise AdminError(f"Request already {request.status.value}", status_code=409)

    request.status = (
        ConnectorAccessRequestStatus.APPROVED if approve else ConnectorAccessRequestStatus.DENIED
    )
    request.reviewed_by = admin_id
    request.reviewed_at = datetime.now(timezone.utc)
    await session.flush()
    return request


async def approve_connector_access_request(
    session: AsyncSession, request_id: uuid.UUID, *, admin_id: uuid.UUID
) -> ConnectorAccessRequest:
    return await _review_connector_access_request(session, request_id, admin_id=admin_id, approve=True)


async def deny_connector_access_request(
    session: AsyncSession, request_id: uuid.UUID, *, admin_id: uuid.UUID
) -> ConnectorAccessRequest:
    return await _review_connector_access_request(session, request_id, admin_id=admin_id, approve=False)


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
