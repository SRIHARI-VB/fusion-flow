"""`/api/v1/businesses` — the tenant's own view of the businesses it belongs to."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from fusionflow.core.deps import CurrentUserDep, SessionDep, TenantContext, TenantContextDep, require_role
from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.auth.http import set_refresh_cookie, to_token_response
from fusionflow.modules.auth.models import User
from fusionflow.modules.auth.schemas import TokenResponse
from fusionflow.modules.auth.service import AuthError
from fusionflow.modules.auth.service import select_business as select_business_service
from fusionflow.modules.catalog import service as catalog_service
from fusionflow.modules.catalog.models import ProductServiceType
from fusionflow.modules.custom_fields import service as custom_fields_service
from fusionflow.modules.custom_fields.models import EntityType
from fusionflow.modules.customers import service as customers_service
from fusionflow.modules.kb import service as kb_service
from fusionflow.modules.tenancy import service as tenancy_service
from fusionflow.modules.tenancy.models import MembershipRole
from fusionflow.modules.tenancy.schemas import (
    BusinessMembershipOut,
    BusinessOut,
    BusinessUpdateRequest,
    MemberCreateRequest,
    MemberOut,
    MemberUpdateRequest,
)
from fusionflow.modules.workflows import service as workflows_service

# resource_key -> tenant-scoped row-count function, for GET /businesses/mine/resource-usage.
# "custom_fields" is deliberately NOT here - its limit applies per
# entity_type (see custom_fields_service.count_field_definitions's
# docstring), not once per tenant, so it's resolved separately below only
# when the caller tells us which entity_type it's asking about.
_RESOURCE_COUNT_FNS = {
    "products": lambda session, tenant_id: catalog_service.count_products_services(
        session, tenant_id, entity_type=ProductServiceType.PRODUCT
    ),
    "services": lambda session, tenant_id: catalog_service.count_products_services(
        session, tenant_id, entity_type=ProductServiceType.SERVICE
    ),
    "coupons": catalog_service.count_coupons,
    "offers": catalog_service.count_offers,
    "customers": customers_service.count_customers,
    "kb": kb_service.count_articles,
    "workflows": workflows_service.count_workflows,
}

router = APIRouter(prefix="/businesses", tags=["businesses"])


@router.get("/mine", response_model=list[BusinessMembershipOut])
async def list_my_businesses(
    user: CurrentUserDep, session: SessionDep
) -> list[BusinessMembershipOut]:
    """Businesses the caller is a member of, with their role in each.

    Intentionally depends only on `get_current_user`, not on tenant
    context: a pre-tenant token must be able to call this to render the
    business picker.
    """
    return await tenancy_service.list_business_memberships(session, user.id)


@router.get("/mine/feature-flags", response_model=dict[str, bool])
async def my_feature_flags(context: TenantContextDep, session: SessionDep) -> dict[str, bool]:
    """`{flag_key: enabled}` for every known flag, resolved for the active
    tenant - lets a frontend decide what to show without duplicating the
    resolution logic client-side. Not currently called by any frontend
    (the Support Agent page/nav is gated by module entitlement instead,
    not a feature flag - see `modules.admin.service.KNOWN_FEATURE_FLAGS`'s
    docstring for why); kept as working infrastructure for the next
    behavior-level toggle, see
    `modules.admin.service.resolve_known_flags_for_tenant`'s docstring for
    a worked example of when this is the right tool.
    """
    return await admin_service.resolve_known_flags_for_tenant(session, context.tenant_id)


@router.get("/mine/resource-usage", response_model=dict[str, dict[str, int | None]])
async def my_resource_usage(
    context: TenantContextDep,
    session: SessionDep,
    custom_fields_entity_type: EntityType | None = Query(default=None),
) -> dict[str, dict[str, int | None]]:
    """`{resource_key: {"limit": int|null, "current": int}}` for every
    limitable resource - lets the web app show "42/50 products" and
    disable "New product" at the limit without duplicating the
    tenant-override/plan/unlimited resolution client-side. The backend
    403 on the create route is the actual boundary; this is a UX nicety
    on top of it.

    `custom_fields` is resolved separately from the rest, only when
    `custom_fields_entity_type` is passed, since its limit applies per
    entity_type rather than once per tenant (see
    `custom_fields_service.count_field_definitions`'s docstring) - the
    Custom Fields settings page passes whichever tab is currently open.
    """
    usage: dict[str, dict[str, int | None]] = {}
    for resource_key, count_fn in _RESOURCE_COUNT_FNS.items():
        limit = await admin_service.get_resource_limit(
            session, tenant_id=context.tenant_id, resource_key=resource_key
        )
        current = await count_fn(session, context.tenant_id)
        usage[resource_key] = {"limit": limit, "current": current}

    if custom_fields_entity_type is not None:
        # Per-entity-type catalog key (see custom_fields/router.py's
        # matching resolution), not the plain "custom_fields" module-gate
        # key - the response key stays "custom_fields" regardless of
        # entity_type so the frontend's lookup doesn't need to change.
        limit = await admin_service.get_resource_limit(
            session,
            tenant_id=context.tenant_id,
            resource_key=f"custom_fields_{custom_fields_entity_type.value}",
        )
        current = await custom_fields_service.count_field_definitions(
            session, context.tenant_id, entity_type=custom_fields_entity_type
        )
        usage["custom_fields"] = {"limit": limit, "current": current}

    return usage


@router.post("/{business_id}/switch", response_model=TokenResponse)
async def switch_business(
    business_id: uuid.UUID,
    response: Response,
    user: CurrentUserDep,
    session: SessionDep,
) -> TokenResponse:
    """Alias of POST /auth/select-business, addressed by path.

    Same service call, so the token/cookie semantics (including "one
    active refresh-token family per business") are identical.
    """
    try:
        issued = await select_business_service(session, user=user, business_id=business_id)
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    set_refresh_cookie(response, issued.refresh_token_raw)
    return to_token_response(issued)


@router.patch("/{business_id}", response_model=BusinessOut)
async def update_business(
    business_id: uuid.UUID,
    payload: BusinessUpdateRequest,
    session: SessionDep,
    context: TenantContext = Depends(require_role(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> BusinessOut:
    """Update the *active* business profile. Owner/admin only.

    `business_id` must match the token's `tenant_id`; editing some other
    business requires switching to it first. This keeps the route inside
    the tenant's RLS scope instead of introducing a cross-tenant write
    path.
    """
    if business_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Switch to that business before editing it",
        )

    business = await tenancy_service.get_business(session, business_id)
    if business is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Business not found")

    await tenancy_service.update_business(session, business, payload)
    await session.commit()
    await session.refresh(business)
    return BusinessOut.model_validate(business)


@router.post("/{business_id}/members", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
async def create_business_member(
    business_id: uuid.UUID,
    payload: MemberCreateRequest,
    session: SessionDep,
    context: TenantContext = Depends(require_role(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> MemberOut:
    """Add a new team member to the *active* business. Owner/admin only,
    same cross-tenant guard as this router's other business-scoped routes.

    There is no email-invite-link flow in this app - the new member's
    password is set directly here by the caller and must be communicated
    out-of-band (no transactional email sending exists anywhere in this
    codebase). The account is immediately active.
    """
    if business_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Switch to that business before adding members to it",
        )
    if payload.role == MembershipRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot grant Owner through this endpoint",
        )

    existing = await tenancy_service.get_user_by_email(session, payload.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists",
        )

    _user, membership = await tenancy_service.create_member(
        session,
        business_id=business_id,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        is_doctor=payload.is_doctor,
    )
    await session.commit()

    return MemberOut(
        id=membership.id,
        email=_user.email,
        role=membership.role,
        invited_at=membership.invited_at,
        accepted_at=membership.accepted_at,
        is_doctor=membership.is_doctor,
    )


@router.get("/{business_id}/members", response_model=list[MemberOut])
async def list_business_members(
    business_id: uuid.UUID,
    session: SessionDep,
    context: TenantContext = Depends(require_role(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> list[MemberOut]:
    """Team members of the *active* business. Owner/admin only.

    Same cross-tenant guard as `PATCH /{business_id}`: this is not a
    generic "look up any business's members" endpoint, only the caller's
    currently-active one.
    """
    if business_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Switch to that business before viewing its members",
        )

    return [
        MemberOut(
            id=membership.id,
            email=user.email,
            role=membership.role,
            invited_at=membership.invited_at,
            accepted_at=membership.accepted_at,
            is_doctor=membership.is_doctor,
        )
        for membership, user in await tenancy_service.list_members_of_business(session, business_id)
    ]


@router.patch("/{business_id}/members/{membership_id}", response_model=MemberOut)
async def update_business_member(
    business_id: uuid.UUID,
    membership_id: uuid.UUID,
    payload: MemberUpdateRequest,
    session: SessionDep,
    context: TenantContext = Depends(require_role(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> MemberOut:
    """Update a team member's doctor flag. Owner/admin only - same
    cross-tenant guard as the other `{business_id}`-scoped routes in this
    router."""
    if business_id != context.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Switch to that business before editing its members",
        )

    membership = await tenancy_service.get_membership_by_id(
        session, business_id=business_id, membership_id=membership_id
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    await tenancy_service.update_membership_is_doctor(session, membership, is_doctor=payload.is_doctor)
    await session.commit()
    await session.refresh(membership)

    user = await session.get(User, membership.user_id)
    return MemberOut(
        id=membership.id,
        email=user.email if user else "",
        role=membership.role,
        invited_at=membership.invited_at,
        accepted_at=membership.accepted_at,
        is_doctor=membership.is_doctor,
    )
