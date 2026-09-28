"""Business/membership domain logic.

None of these functions commit - callers (routers, auth.service) own the
transaction boundary so that signup can create user + business + membership
atomically.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.core.security import hash_password
from fusionflow.modules.admin.models import Plan
from fusionflow.modules.auth.models import User
from fusionflow.modules.tenancy.models import Business, BusinessStatus, Membership, MembershipRole
from fusionflow.modules.tenancy.schemas import BusinessMembershipOut, BusinessUpdateRequest

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    slug = _SLUG_STRIP.sub("-", value.strip().lower()).strip("-")
    return slug[:100] or "business"


async def generate_unique_slug(session: AsyncSession, name: str) -> str:
    """Derive a slug from `name`, suffixing `-2`, `-3`, ... on collision.

    Racy by construction (two concurrent signups can pick the same slug);
    the UNIQUE index on `businesses.slug` is the real guard and turns the
    race into an IntegrityError the caller can retry, rather than a
    duplicate.
    """
    base = slugify(name)
    existing = set(
        (await session.execute(select(Business.slug).where(Business.slug.like(f"{base}%"))))
        .scalars()
        .all()
    )
    if base not in existing:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base}-{suffix}"
        if candidate not in existing:
            return candidate
    return f"{base}-{uuid.uuid4().hex[:8]}"


async def create_business_with_owner(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    vertical: str | None = None,
    status: BusinessStatus = BusinessStatus.ACTIVE,
) -> tuple[Business, Membership]:
    """Create a business and make `user_id` its owner. Does not commit.

    `status` defaults to `ACTIVE` (unchanged existing behavior, so this stays
    a no-op for every caller/test that doesn't pass it explicitly).
    `modules.auth.service.signup` passes `BusinessStatus.PENDING_APPROVAL`
    explicitly now that self-serve signup requires admin approval before
    login works.
    """
    now = datetime.now(timezone.utc)
    business = Business(
        id=uuid.uuid4(),
        name=name,
        slug=await generate_unique_slug(session, name),
        vertical=vertical,
        status=status,
    )
    membership = Membership(
        id=uuid.uuid4(),
        user_id=user_id,
        business_id=business.id,
        role=MembershipRole.OWNER,
        accepted_at=now,  # self-serve signup: the owner accepts implicitly
    )
    session.add(business)
    session.add(membership)
    await session.flush()
    return business, membership


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return (
        await session.execute(select(User).where(User.email == email.strip().lower()))
    ).scalar_one_or_none()


async def create_member(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    email: str,
    password: str,
    role: MembershipRole,
    is_doctor: bool = False,
) -> tuple[User, Membership]:
    """Create a brand-new user + an immediately-accepted membership on an
    EXISTING business. Does not commit; does not check for a duplicate
    email - callers must do that first (see `auth.service.signup`'s
    identical duplicate-email check, which this mirrors rather than
    reuses, since that one commits as part of the signup transaction and
    this one is a separate write path).

    Unlike `create_business_with_owner` (which only ever assigns
    `OWNER`), this is the path for an owner/admin adding a colleague to
    their OWN existing business - there is no email-based invite-link
    flow in this app (no transactional email sending exists anywhere in
    this codebase), so the new member's password is set directly by
    whoever adds them and must be communicated out-of-band. `accepted_at`
    is set immediately (no separate "pending invite" acceptance step),
    matching the self-serve signup owner's own immediate acceptance.
    """
    now = datetime.now(timezone.utc)
    user = User(
        id=uuid.uuid4(),
        email=email.strip().lower(),
        password_hash=hash_password(password),
    )
    session.add(user)
    await session.flush()

    membership = Membership(
        id=uuid.uuid4(),
        user_id=user.id,
        business_id=business_id,
        role=role,
        is_doctor=is_doctor,
        accepted_at=now,
    )
    session.add(membership)
    await session.flush()
    return user, membership


async def list_memberships_for_user(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Membership, Business]]:
    """Every accepted (membership, business) pair for a user, oldest first."""
    rows = await session.execute(
        select(Membership, Business)
        .join(Business, Business.id == Membership.business_id)
        .where(Membership.user_id == user_id, Membership.accepted_at.is_not(None))
        .order_by(Membership.invited_at)
    )
    return [(m, b) for m, b in rows.all()]


async def list_business_memberships(
    session: AsyncSession, user_id: uuid.UUID
) -> list[BusinessMembershipOut]:
    """DTO form of `list_memberships_for_user`, plus each business's plan name.

    Deliberately does its own query (rather than reusing
    `list_memberships_for_user` + a second round-trip) so `GET
    /businesses/mine` can show a real plan name - `list_memberships_for_user`
    itself stays untouched since `modules.auth.service`'s login/refresh
    paths also call it and passing a plan name through there isn't needed
    for those latency-sensitive flows (the frontend already falls back to
    "Free Plan" until this endpoint's response arrives).
    """
    rows = await session.execute(
        select(Membership, Business, Plan.name)
        .join(Business, Business.id == Membership.business_id)
        .outerjoin(Plan, Plan.id == Business.plan_id)
        .where(Membership.user_id == user_id, Membership.accepted_at.is_not(None))
        .order_by(Membership.invited_at)
    )
    return [
        to_business_membership_out(membership, business, plan_name=plan_name)
        for membership, business, plan_name in rows.all()
    ]


def to_business_membership_out(
    membership: Membership, business: Business, *, plan_name: str | None = None
) -> BusinessMembershipOut:
    return BusinessMembershipOut(
        id=business.id,
        name=business.name,
        slug=business.slug,
        vertical=business.vertical,
        status=business.status,
        role=membership.role,
        messaging_paused=business.messaging_paused,
        onboarding_completed_at=business.onboarding_completed_at,
        plan_name=plan_name,
        is_doctor=membership.is_doctor,
    )


async def get_membership(
    session: AsyncSession, *, user_id: uuid.UUID, business_id: uuid.UUID
) -> Membership | None:
    return (
        await session.execute(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.business_id == business_id,
                Membership.accepted_at.is_not(None),
            )
        )
    ).scalar_one_or_none()


async def get_business(session: AsyncSession, business_id: uuid.UUID) -> Business | None:
    return await session.get(Business, business_id)


async def update_business(
    session: AsyncSession, business: Business, payload: BusinessUpdateRequest
) -> Business:
    """Apply a partial update. Does not commit."""
    if payload.name is not None:
        business.name = payload.name
    if payload.vertical is not None:
        business.vertical = payload.vertical
    if payload.mark_onboarding_complete and business.onboarding_completed_at is None:
        business.onboarding_completed_at = datetime.now(timezone.utc)
    if payload.messaging_paused is not None:
        business.messaging_paused = payload.messaging_paused
    await session.flush()
    return business


async def list_members_of_business(
    session: AsyncSession, business_id: uuid.UUID
) -> list[tuple[Membership, User]]:
    """Every (membership, user) pair for a business, oldest invite first.

    Distinct from `list_memberships_for_user`, which is keyed by user_id and
    used for the login/business-picker path; this one is keyed by
    business_id and used for the settings page's team-members list.
    """
    rows = await session.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.business_id == business_id)
        .order_by(Membership.invited_at)
    )
    return [(m, u) for m, u in rows.all()]


async def get_membership_by_id(
    session: AsyncSession, *, business_id: uuid.UUID, membership_id: uuid.UUID
) -> Membership | None:
    return (
        await session.execute(
            select(Membership).where(
                Membership.id == membership_id, Membership.business_id == business_id
            )
        )
    ).scalar_one_or_none()


async def update_membership_is_doctor(
    session: AsyncSession, membership: Membership, *, is_doctor: bool
) -> Membership:
    """Apply the doctor-flag update. Does not commit - matches
    `update_business`'s convention, the router owns the transaction
    boundary."""
    membership.is_doctor = is_doctor
    await session.flush()
    return membership


async def count_memberships(session: AsyncSession, user_id: uuid.UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(Membership)
                .where(Membership.user_id == user_id, Membership.accepted_at.is_not(None))
            )
        ).scalar_one()
    )
