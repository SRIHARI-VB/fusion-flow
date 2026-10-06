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
    WorkflowComponent,
    WorkflowNodeTemplate,
    WorkflowStarterTemplate,
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

# Catalog keys that exist ONLY to carry a per-entity-type resource-count
# limit (see custom_fields/router.py::create_definition) - never checked by
# require_module_access, so granting/revoking one via the "Modules &
# connectors" panel would silently do nothing. Excluded from that panel's
# catalog listing below; see RESOURCE_LIMIT_KEYS for the mirror-image
# problem (catalog keys that DO gate module access but enforce no count
# limit, which get excluded from the resource-limits panels instead).
LIMIT_ONLY_KEYS = frozenset(
    {"custom_fields_product", "custom_fields_service", "custom_fields_coupon", "custom_fields_offer"}
)

# Catalog keys that `GET/PUT /admin/plans/{id}/resource-limits` and
# `GET/PUT/DELETE /admin/tenants/{id}/resource-limits` actually enforce a
# count against - every other catalog key (whatsapp/razorpay, orders/
# payments/tickets/support_agent, and the plain "custom_fields" module-gate
# key itself) would accept a number with zero effect, so the resource-limit
# admin surfaces filter down to exactly this set instead of listing the
# whole catalog and leaving those as confusing dead rows. Keep in sync by
# hand with `modules.tenancy.router._RESOURCE_COUNT_FNS` (the 7 non-custom-
# field keys) plus the 4 `LIMIT_ONLY_KEYS` above (enforced inline by
# `custom_fields/router.py::create_definition`, not the generic dependency).
RESOURCE_LIMIT_KEYS = frozenset(
    {"products", "services", "coupons", "offers", "customers", "kb", "workflows"} | LIMIT_ONLY_KEYS
)


async def get_tenant_module_access(session: AsyncSession, business_id: uuid.UUID) -> list[dict[str, Any]]:
    """Full connector/module catalog (minus `LIMIT_ONLY_KEYS`) + this
    tenant's resolved `access_status` + whether an admin override exists,
    for the admin's per-tenant "Modules & connectors" panel. Same
    `set_tenant_context`-on-the-request-session pattern as
    `get_tenant_connector_health` above - no `app.current_tenant_id` is set
    by default under `/api/admin/*`."""
    if not _CONNECTORS_AVAILABLE:
        return []

    await set_tenant_context(session, business_id)
    from fusionflow.modules.connectors.models import RoleModuleRestriction
    from fusionflow.modules.connectors.module_dependencies import MODULE_DEPENDENCIES, dependents_of

    types = [t for t in await connector_service.list_connector_types(session) if t.key not in LIMIT_ONLY_KEYS]
    # Single source of truth (override > bundle > request, plus grandfathering).
    access_map = await connector_service.resolve_module_access_map(
        session, tenant_id=business_id, connector_types=types, role=None
    )
    overrides = await connector_service.get_connector_access_overrides(session, tenant_id=business_id)
    restriction_rows = (
        await session.execute(
            select(RoleModuleRestriction.connector_type_id, RoleModuleRestriction.role).where(
                RoleModuleRestriction.tenant_id == business_id
            )
        )
    ).all()
    restrictions_by_type: dict[uuid.UUID, list[str]] = {}
    for type_id, role in restriction_rows:
        restrictions_by_type.setdefault(type_id, []).append(getattr(role, "value", str(role)))
    return [
        {
            "connector_type_id": t.id,
            "connector_type_key": t.key,
            "display_name": t.display_name,
            "category": t.category.value,
            "access_status": access_map.get(t.id, "not_requested"),
            "has_override": t.id in overrides,
            "override_granted": overrides[t.id].granted if t.id in overrides else None,
            "role_restrictions": sorted(restrictions_by_type.get(t.id, [])),
            "depends_on": list(MODULE_DEPENDENCIES.get(t.key, [])),
            "dependents": dependents_of(t.key),
        }
        for t in types
    ]


async def get_connector_revoke_impact(
    session: AsyncSession, business_id: uuid.UUID, type_key: str
) -> dict[str, Any]:
    """What revoking `type_key` for this tenant would affect - shown in the
    admin confirmation dialog before the override is written."""
    if not _CONNECTORS_AVAILABLE:
        raise AdminError("modules.connectors is not available in this checkout", status_code=501)

    await set_tenant_context(session, business_id)
    from fusionflow.modules.connectors.models import ConnectorState, RoleModuleRestriction
    from fusionflow.modules.connectors.module_dependencies import dependents_of
    from fusionflow.modules.workflows.engine import entitlement
    from fusionflow.modules.workflows.models import Workflow, WorkflowVersion

    connector_type = await connector_service.get_connector_type_by_key(session, type_key)
    if connector_type is None:
        raise AdminError(f"Unknown connector type: {type_key!r}", status_code=404)

    all_types = {t.key: t for t in await connector_service.list_connector_types(session)}

    dependents: list[dict[str, Any]] = []
    dependent_types = [all_types[k] for k in dependents_of(type_key) if k in all_types]
    if dependent_types:
        dep_map = await connector_service.resolve_module_access_map(
            session, tenant_id=business_id, connector_types=dependent_types, role=None
        )
        dependents = [
            {"key": t.key, "display_name": t.display_name, "access_status": dep_map.get(t.id, "not_requested")}
            for t in dependent_types
            if dep_map.get(t.id) == "granted"
        ]

    workflow_rows = (
        await session.execute(
            select(Workflow, WorkflowVersion)
            .join(WorkflowVersion, WorkflowVersion.id == Workflow.current_published_version_id)
            .where(Workflow.tenant_id == business_id)
        )
    ).all()
    published_workflows = [
        {"id": wf.id, "name": wf.name}
        for wf, version in workflow_rows
        if type_key in entitlement.graph_required_keys_from_json(version.compiled_graph or version.graph)
    ]

    connected_instances = 0
    if connector_type.category.value != "feature":
        connected_instances = (
            await session.execute(
                select(func.count())
                .select_from(ConnectorInstance)
                .where(
                    ConnectorInstance.tenant_id == business_id,
                    ConnectorInstance.connector_type_id == connector_type.id,
                    ConnectorInstance.state == ConnectorState.CONNECTED,
                )
            )
        ).scalar_one()

    roles = (
        await session.execute(
            select(RoleModuleRestriction.role).where(
                RoleModuleRestriction.tenant_id == business_id,
                RoleModuleRestriction.connector_type_id == connector_type.id,
            )
        )
    ).scalars().all()

    active_users_count = (
        await session.execute(
            select(func.count())
            .select_from(Membership)
            .where(Membership.business_id == business_id, Membership.accepted_at.is_not(None))
        )
    ).scalar_one()

    return {
        "type_key": connector_type.key,
        "display_name": connector_type.display_name,
        "dependents": dependents,
        "published_workflows": published_workflows,
        "connected_instances": int(connected_instances),
        "role_restrictions": [{"role": getattr(r, "value", str(r))} for r in sorted(set(roles), key=str)],
        "active_users_count": int(active_users_count),
    }


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
# something today.
#
# `support_agent_enabled` used to be the one real entry here (gating the
# /support-agent nav item + route) but was superseded when
# `modules.connectors`'s module-entitlement system grew a `support_agent`
# FEATURE-category catalog key with its own template-bundling/request/
# revoke support (see `modules.connectors.deps.require_module_access`,
# now what actually gates that route in `frontend/web/src/App.tsx`) -
# removed from here rather than left as dead weight an admin could toggle
# with zero effect. This is also the deciding line for what belongs in
# this catalog going forward vs. the module system: a *whole
# page/route/module* belongs in `ConnectorType`; a *behavior toggle
# inside* an already-accessible module (a beta UI variant, a gradual
# rollout, a kill-switch narrower than "hide the whole page") belongs
# here. See `resolve_known_flags_for_tenant`'s docstring for a worked
# example of the latter.
KNOWN_FEATURE_FLAGS: list[dict[str, str | bool]] = [
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
    `modules.tenancy.router`) - not yet called by any frontend (the one
    flag that used to back a real UI decision, `support_agent_enabled`,
    was superseded by module entitlement - see `KNOWN_FEATURE_FLAGS`'s
    docstring), but the endpoint/resolver stay in place as working
    infrastructure for the next flag that DOES need this shape.

    Worked example of what belongs here (vs. the module system): suppose
    the workflow engine ships a new "AI condition" node type behind
    `advanced_workflows`. Every tenant can already open `/workflows` (a
    module they're entitled to) - the flag doesn't gate the page, it
    gates one row in the node palette returned by `GET
    /workflows/node-types`. That handler would call
    `is_feature_enabled(session, "advanced_workflows", tenant_id)` and
    filter the AI condition node out of the response for tenants where
    it's `False` - letting you roll it out to a handful of tenants first,
    same as any tenant-override/plan-based gradual rollout, without
    needing a whole new catalog entry, template bundle, or request/
    approve flow the way a new module would.

    A flag that doesn't exist yet in the `feature_flags` table (nobody
    has created it in the admin panel yet) resolves to `False` via the
    same unknown-key-is-safe behavior `is_feature_enabled` already has.
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


async def list_plan_resource_limits(session: AsyncSession, plan_id: uuid.UUID) -> list[dict[str, Any]]:
    """Every key in `RESOURCE_LIMIT_KEYS` + this plan's configured limit
    (`None` if unset - unlimited), for the admin plan editor's resource-
    limits grid. Enriched the same way `get_tenant_resource_limits` is,
    rather than returning bare `PlanResourceLimit` rows, so the UI can
    render an input for every limitable key, not just the ones already
    configured. Filtered to `RESOURCE_LIMIT_KEYS` rather than the whole
    catalog - see that constant's docstring for why."""
    if not _CONNECTORS_AVAILABLE:
        return []

    types = [t for t in await connector_service.list_connector_types(session) if t.key in RESOURCE_LIMIT_KEYS]
    limits = {
        row.connector_type_id: row.max_count
        for row in (
            await session.execute(select(PlanResourceLimit).where(PlanResourceLimit.plan_id == plan_id))
        )
        .scalars()
        .all()
    }
    return [
        {
            "connector_type_id": t.id,
            "resource_key": t.key,
            "display_name": t.display_name,
            "max_count": limits.get(t.id),
        }
        for t in types
    ]


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
    """Every key in `RESOURCE_LIMIT_KEYS`'s effective limit + source, for
    the admin's per-tenant resource-limits panel. Filtered the same way
    `list_plan_resource_limits` is - see `RESOURCE_LIMIT_KEYS`'s docstring."""
    if not _CONNECTORS_AVAILABLE:
        return []

    await set_tenant_context(session, business_id)
    types = [t for t in await connector_service.list_connector_types(session) if t.key in RESOURCE_LIMIT_KEYS]
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
                "resource_key": t.key,
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


# --- Workflow node templates (admin-managed palette entries, Part D) --------


async def list_workflow_node_templates(session: AsyncSession, *, active_only: bool = False) -> list[WorkflowNodeTemplate]:
    query = select(WorkflowNodeTemplate).order_by(WorkflowNodeTemplate.label)
    if active_only:
        query = query.where(WorkflowNodeTemplate.is_active.is_(True))
    return list((await session.execute(query)).scalars().all())


async def get_workflow_node_template(
    session: AsyncSession, template_id: uuid.UUID
) -> WorkflowNodeTemplate | None:
    return await session.get(WorkflowNodeTemplate, template_id)


async def create_workflow_node_template(
    session: AsyncSession,
    *,
    key: str,
    label: str,
    description: str | None,
    category: str,
    base_node_type: str,
    icon: str | None,
    default_config: dict[str, Any],
    config_schema_overrides: dict[str, Any] | None,
    is_active: bool,
    required_connector_type_key: str | None,
) -> WorkflowNodeTemplate:
    existing = (
        await session.execute(select(WorkflowNodeTemplate).where(WorkflowNodeTemplate.key == key))
    ).scalar_one_or_none()
    if existing is not None:
        raise AdminError(f"Workflow node template '{key}' already exists", status_code=409)

    template = WorkflowNodeTemplate(
        id=uuid.uuid4(),
        key=key,
        label=label,
        description=description,
        category=category,
        base_node_type=base_node_type,
        icon=icon,
        default_config=default_config,
        config_schema_overrides=config_schema_overrides,
        is_active=is_active,
        required_connector_type_key=required_connector_type_key,
    )
    session.add(template)
    await session.flush()
    return template


async def update_workflow_node_template(
    session: AsyncSession,
    template_id: uuid.UUID,
    *,
    label: str | None,
    description: str | None,
    category: str | None,
    icon: str | None,
    default_config: dict[str, Any] | None,
    config_schema_overrides: dict[str, Any] | None,
    is_active: bool | None,
    required_connector_type_key: str | None = None,
) -> WorkflowNodeTemplate:
    """`base_node_type` is deliberately not editable after creation - it
    determines which executor's config schema this template narrows,
    and swapping it out from under an already-built workflow graph that
    references this template's `key` would silently change what that
    node actually does at runtime. Delete and recreate instead."""
    template = await get_workflow_node_template(session, template_id)
    if template is None:
        raise AdminError("Workflow node template not found", status_code=404)
    if label is not None:
        template.label = label
    if description is not None:
        template.description = description
    if category is not None:
        template.category = category
    if icon is not None:
        template.icon = icon
    if default_config is not None:
        template.default_config = default_config
    if config_schema_overrides is not None:
        template.config_schema_overrides = config_schema_overrides
    if is_active is not None:
        template.is_active = is_active
    if required_connector_type_key is not None:
        template.required_connector_type_key = required_connector_type_key
    await session.flush()
    return template


async def delete_workflow_node_template(session: AsyncSession, template_id: uuid.UUID) -> None:
    template = await get_workflow_node_template(session, template_id)
    if template is None:
        raise AdminError("Workflow node template not found", status_code=404)
    await session.delete(template)
    await session.flush()


# --- Workflow starter templates (composable-builder redesign, Phase 6) ------


async def list_workflow_starter_templates(
    session: AsyncSession, *, active_only: bool = False
) -> list[WorkflowStarterTemplate]:
    query = select(WorkflowStarterTemplate).order_by(WorkflowStarterTemplate.name)
    if active_only:
        query = query.where(WorkflowStarterTemplate.is_active.is_(True))
    return list((await session.execute(query)).scalars().all())


async def get_workflow_starter_template(
    session: AsyncSession, template_id: uuid.UUID
) -> WorkflowStarterTemplate | None:
    return await session.get(WorkflowStarterTemplate, template_id)


async def get_workflow_starter_template_by_key(
    session: AsyncSession, key: str
) -> WorkflowStarterTemplate | None:
    return (
        await session.execute(select(WorkflowStarterTemplate).where(WorkflowStarterTemplate.key == key))
    ).scalar_one_or_none()


async def create_workflow_starter_template(
    session: AsyncSession,
    *,
    key: str,
    name: str,
    description: str | None,
    category: str,
    icon: str | None,
    graph_json: dict[str, Any],
    required_object_types: list[dict[str, Any]] | None,
    is_active: bool,
    setup_notes: str | None = None,
) -> WorkflowStarterTemplate:
    existing = (
        await session.execute(select(WorkflowStarterTemplate).where(WorkflowStarterTemplate.key == key))
    ).scalar_one_or_none()
    if existing is not None:
        raise AdminError(f"Workflow starter template '{key}' already exists", status_code=409)

    template = WorkflowStarterTemplate(
        id=uuid.uuid4(),
        key=key,
        name=name,
        description=description,
        category=category,
        icon=icon,
        graph_json=graph_json,
        required_object_types=required_object_types,
        setup_notes=setup_notes,
        is_active=is_active,
    )
    session.add(template)
    await session.flush()
    return template


async def update_workflow_starter_template(
    session: AsyncSession,
    template_id: uuid.UUID,
    *,
    name: str | None,
    description: str | None,
    category: str | None,
    icon: str | None,
    graph_json: dict[str, Any] | None,
    required_object_types: list[dict[str, Any]] | None,
    is_active: bool | None,
    setup_notes: str | None = None,
) -> WorkflowStarterTemplate:
    template = await get_workflow_starter_template(session, template_id)
    if template is None:
        raise AdminError("Workflow starter template not found", status_code=404)
    if name is not None:
        template.name = name
    if description is not None:
        template.description = description
    if category is not None:
        template.category = category
    if icon is not None:
        template.icon = icon
    if graph_json is not None:
        template.graph_json = graph_json
    if required_object_types is not None:
        template.required_object_types = required_object_types
    if setup_notes is not None:
        template.setup_notes = setup_notes
    if is_active is not None:
        template.is_active = is_active
    await session.flush()
    return template


async def delete_workflow_starter_template(session: AsyncSession, template_id: uuid.UUID) -> None:
    template = await get_workflow_starter_template(session, template_id)
    if template is None:
        raise AdminError("Workflow starter template not found", status_code=404)
    await session.delete(template)
    await session.flush()


def compute_workflow_purpose(graph: dict[str, Any]) -> str | None:
    """Which "New Workflow" purpose (`"automation"` vs. `"broadcast"`) a
    starter template's own stored `graph_json` belongs under - server-
    computed from the template's root trigger node, not a stored column,
    so the two never drift apart the way a hand-maintained `purpose`
    field on `WorkflowStarterTemplate` could. Called by
    `workflows.router.get_starter_templates` right next to where the
    graph's other derived, informational fields would be computed (see
    that route for the call site).

    The root trigger node is the one whose own `id` is `"trigger"` — every
    template in `scripts/seed_workflow_starter_templates.py` names its
    trigger node that way by convention (see that module's `_node` calls) —
    falling back to the first node whose `type` is `"trigger"` for a
    hand-authored graph that doesn't happen to use that id.

    That node's `data.nodeType` is looked up against `trigger_registry`
    (`engine.registry`) to read the real registered `TriggerDefinition`'s
    `applicable_purposes` — a list like `["automation"]`/`["broadcast"]`
    a trigger type declares itself. `getattr(..., None)` (not direct
    attribute access) is deliberate: `TriggerDefinition` is a separately-
    owned dataclass this function does not define, so this stays safe
    whether or not that field exists yet on a given trigger's definition.
    Only the two single-purpose-exclusive shapes resolve to something -
    `None` (unset, some other shape, an unregistered/deleted node type, or
    no trigger node at all) means "shown for either purpose," never raises.
    """
    from fusionflow.modules.workflows.engine.registry import trigger_registry

    nodes = graph.get("nodes") or []
    trigger_node = next(
        (n for n in nodes if isinstance(n, dict) and n.get("id") == "trigger"), None
    )
    if trigger_node is None:
        trigger_node = next(
            (n for n in nodes if isinstance(n, dict) and n.get("type") == "trigger"), None
        )
    if trigger_node is None:
        return None

    node_type = (trigger_node.get("data") or {}).get("nodeType")
    if not node_type:
        return None

    definition = trigger_registry.get(node_type)
    if definition is None:
        return None

    applicable_purposes = getattr(definition, "applicable_purposes", None)
    if applicable_purposes == ["broadcast"]:
        return "broadcast"
    if applicable_purposes == ["automation"]:
        return "automation"
    return None


# --- Workflow components (insertable fragments, composable-builder redesign) -


async def list_workflow_components(session: AsyncSession, *, active_only: bool = False) -> list[WorkflowComponent]:
    query = select(WorkflowComponent).order_by(WorkflowComponent.name)
    if active_only:
        query = query.where(WorkflowComponent.is_active.is_(True))
    return list((await session.execute(query)).scalars().all())


async def get_workflow_component(session: AsyncSession, component_id: uuid.UUID) -> WorkflowComponent | None:
    return await session.get(WorkflowComponent, component_id)


async def get_workflow_component_by_key(session: AsyncSession, key: str) -> WorkflowComponent | None:
    return (
        await session.execute(select(WorkflowComponent).where(WorkflowComponent.key == key))
    ).scalar_one_or_none()


async def create_workflow_component(
    session: AsyncSession,
    *,
    key: str,
    name: str,
    description: str | None,
    category: str,
    icon: str | None,
    graph_fragment: dict[str, Any],
    required_object_types: list[dict[str, Any]] | None,
    is_active: bool,
    setup_notes: str | None = None,
) -> WorkflowComponent:
    existing = (
        await session.execute(select(WorkflowComponent).where(WorkflowComponent.key == key))
    ).scalar_one_or_none()
    if existing is not None:
        raise AdminError(f"Workflow component '{key}' already exists", status_code=409)

    component = WorkflowComponent(
        id=uuid.uuid4(),
        key=key,
        name=name,
        description=description,
        category=category,
        icon=icon,
        graph_fragment=graph_fragment,
        required_object_types=required_object_types,
        setup_notes=setup_notes,
        is_active=is_active,
    )
    session.add(component)
    await session.flush()
    return component


async def update_workflow_component(
    session: AsyncSession,
    component_id: uuid.UUID,
    *,
    name: str | None,
    description: str | None,
    category: str | None,
    icon: str | None,
    graph_fragment: dict[str, Any] | None,
    required_object_types: list[dict[str, Any]] | None,
    is_active: bool | None,
    setup_notes: str | None = None,
) -> WorkflowComponent:
    component = await get_workflow_component(session, component_id)
    if component is None:
        raise AdminError("Workflow component not found", status_code=404)
    if name is not None:
        component.name = name
    if description is not None:
        component.description = description
    if category is not None:
        component.category = category
    if icon is not None:
        component.icon = icon
    if graph_fragment is not None:
        component.graph_fragment = graph_fragment
    if required_object_types is not None:
        component.required_object_types = required_object_types
    if setup_notes is not None:
        component.setup_notes = setup_notes
    if is_active is not None:
        component.is_active = is_active
    await session.flush()
    return component


async def delete_workflow_component(session: AsyncSession, component_id: uuid.UUID) -> None:
    component = await get_workflow_component(session, component_id)
    if component is None:
        raise AdminError("Workflow component not found", status_code=404)
    await session.delete(component)
    await session.flush()


# --- Auto-derived connector requirements (never hand-maintained) -----------


def compute_required_connector_type_keys(graph: dict[str, Any] | None) -> list[str]:
    """Derives which connector types a starter template's/component's graph
    needs, straight from its own nodes - never a hand-maintained list (which
    would drift the moment an admin edits the graph without also updating
    it). Purely informational for a tenant deciding whether to use a
    template/component, unlike `WorkflowNodeTemplate.required_connector_type_key`
    (which actually hides palette entries) - this never blocks anything.
    """
    # Local import: avoids a circular import - `workflows/service.py`
    # already imports FROM `admin/service.py`, so the reverse (admin
    # importing from workflows.engine) must stay function-scoped.
    from fusionflow.modules.workflows.engine.registry import node_executor_registry, trigger_registry

    keys: set[str] = set()
    for node in (graph or {}).get("nodes", []):
        node_type = (node.get("data") or {}).get("nodeType")
        if not node_type:
            continue
        executor = node_executor_registry.get(node_type)
        if executor is not None and executor.required_connector_type_key:
            keys.add(executor.required_connector_type_key)
            continue
        trigger = trigger_registry.get(node_type)
        if trigger is not None and trigger.required_connector_type_key:
            keys.add(trigger.required_connector_type_key)
    return sorted(keys)


# --- Validate (Part C): reuse the existing publish-time validation logic ---


async def validate_starter_template_graph(
    session: AsyncSession, graph_json: dict[str, Any]
) -> tuple[list["ValidationIssue"], list[str]]:
    """Compiles `graph_json` exactly like `workflows.service.publish_workflow`
    does (template resolution -> composite-branch expansion -> full
    `validate_for_publish`), against a fresh random tenant id since this is
    an admin authoring a global catalog row, not a real tenant - every
    placeholder `connector_instance_id` in a template is expected to fail
    rule 2 (`disconnected_connector_reference`); that is the accepted
    passing bar, matching the seeded-template regression tests' own "zero
    non-connector-reference issues" convention (see
    `tests/test_workflow_starter_templates.py`)."""
    # Local imports: same circular-import reason as
    # `compute_required_connector_type_keys` above.
    from fusionflow.modules.workflows.engine.graph import WorkflowGraph
    from fusionflow.modules.workflows.engine.template_resolution import (
        resolve_composite_branches,
        resolve_node_templates,
    )
    from fusionflow.modules.workflows.validation import ValidationIssue, validate_for_publish

    compiled = await resolve_node_templates(session, graph_json)
    compiled = resolve_composite_branches(compiled)
    graph = WorkflowGraph.from_json(compiled)
    result = await validate_for_publish(session, tenant_id=uuid.uuid4(), graph=graph)
    return result.issues, compute_required_connector_type_keys(compiled)


async def validate_component_graph(
    session: AsyncSession, graph_fragment: dict[str, Any]
) -> tuple[list["ValidationIssue"], list[str]]:
    """Lighter check than `validate_starter_template_graph`: a component is
    a deliberately partial fragment (dangling handles, placeholder tokens
    referencing a node id that doesn't exist in the fragment itself - see
    `WorkflowComponent`'s docstring), so running the full
    `validate_for_publish` (unreachable-node/no-trigger/containment rules)
    against it would produce a wall of expected-but-meaningless errors.
    Instead: for each node, resolve its (already-compiled, real) node type
    against the registry and run just that executor's own `validate_config`
    - the same per-node check `validation.py` rule 1 runs, without the
    whole-graph rules that assume a complete, publishable workflow."""
    # Local import: same circular-import reason as the functions above.
    from pydantic import ValidationError

    from fusionflow.modules.workflows.engine.registry import node_executor_registry
    from fusionflow.modules.workflows.engine.template_resolution import resolve_node_templates
    from fusionflow.modules.workflows.validation import ValidationIssue

    compiled = await resolve_node_templates(session, graph_fragment)
    issues: list[ValidationIssue] = []
    for node in compiled.get("nodes", []):
        node_id = node.get("id")
        data = node.get("data") or {}
        node_type = data.get("nodeType")
        executor = node_executor_registry.get(node_type)
        if executor is None:
            issues.append(
                ValidationIssue(
                    rule="unknown_node_type",
                    severity="error",
                    node_id=node_id,
                    message=f"unknown node type {node_type!r}",
                )
            )
            continue
        try:
            executor.validate_config(data.get("config") or {})
        except ValidationError as exc:
            first = exc.errors()[0] if exc.errors() else None
            detail = first["msg"] if first else str(exc)
            issues.append(
                ValidationIssue(
                    rule="missing_required_fields",
                    severity="error",
                    node_id=node_id,
                    message=f"invalid config for {node_type}: {detail}",
                )
            )
    return issues, compute_required_connector_type_keys(compiled)
