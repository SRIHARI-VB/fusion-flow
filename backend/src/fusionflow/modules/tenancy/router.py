"""`/api/v1/businesses` — the tenant's own view of the businesses it belongs to."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status

from fusionflow.core.deps import CurrentUserDep, SessionDep, TenantContext, require_role
from fusionflow.modules.auth.http import set_refresh_cookie, to_token_response
from fusionflow.modules.auth.schemas import TokenResponse
from fusionflow.modules.auth.service import AuthError
from fusionflow.modules.auth.service import select_business as select_business_service
from fusionflow.modules.tenancy import service as tenancy_service
from fusionflow.modules.tenancy.models import MembershipRole
from fusionflow.modules.tenancy.schemas import (
    BusinessMembershipOut,
    BusinessOut,
    BusinessUpdateRequest,
    MemberOut,
)

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
            email=user.email,
            role=membership.role,
            invited_at=membership.invited_at,
            accepted_at=membership.accepted_at,
        )
        for membership, user in await tenancy_service.list_members_of_business(session, business_id)
    ]
