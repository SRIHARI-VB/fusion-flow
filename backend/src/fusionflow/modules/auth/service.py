"""Auth domain logic: signup, login, refresh rotation, logout, business switch.

Deliberately framework-free (raises `AuthError`, not `HTTPException`) so the
flows can be unit-tested without spinning up FastAPI; `router.py` maps
`AuthError` to an HTTP response.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.config import get_settings
from fusionflow.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    refresh_token_expiry,
    verify_password,
)
from fusionflow.modules.auth.models import RefreshToken, User
from fusionflow.modules.tenancy import service as tenancy_service
from fusionflow.modules.tenancy.models import Business, BusinessStatus, Membership, MembershipRole

settings = get_settings()


class AuthError(Exception):
    """Domain-level auth failure. `status_code` is the HTTP status to emit."""

    def __init__(self, detail: str, status_code: int = 401) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


@dataclass
class IssuedSession:
    """Everything the router needs to answer a successful auth call."""

    user: User
    access_token: str
    refresh_token_raw: str
    expires_in: int
    requires_business_selection: bool = False
    memberships: list[tuple[Membership, Business]] = field(default_factory=list)


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    """Hash of a throwaway password, verified against when the email is unknown.

    Keeps the wall-clock cost of "unknown email" and "wrong password"
    roughly equal so login cannot be used to enumerate accounts.
    """
    return hash_password("fusionflow-timing-equalizer")


async def _create_refresh_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    business_id: uuid.UUID | None,
    family_id: uuid.UUID | None = None,
) -> tuple[RefreshToken, str]:
    raw, token_hash = generate_refresh_token()
    row = RefreshToken(
        id=uuid.uuid4(),
        user_id=user_id,
        token_hash=token_hash,
        family_id=family_id or uuid.uuid4(),
        business_id=business_id,
        expires_at=refresh_token_expiry(),
    )
    session.add(row)
    await session.flush()
    return row, raw


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    """Revoke every still-live token in a rotation chain (theft response)."""
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(timezone.utc))
    )


async def _revoke_active_tokens_for_business(
    session: AsyncSession, *, user_id: uuid.UUID, business_id: uuid.UUID | None
) -> None:
    """Enforce "one active refresh-token family per business".

    Documented tradeoff (plan Risk #5): switching to a business in one tab
    invalidates any other tab already holding a session for that same
    business, on its next refresh.
    """
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.user_id == user_id,
            RefreshToken.business_id.is_(business_id) if business_id is None
            else RefreshToken.business_id == business_id,
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )


async def _issue_for_business(
    session: AsyncSession,
    *,
    user: User,
    business_id: uuid.UUID,
    role: MembershipRole,
    family_id: uuid.UUID | None = None,
) -> IssuedSession:
    access_token = create_access_token(
        sub=user.id,
        tenant_id=business_id,
        role=role.value,
        platform_admin=user.is_platform_admin,
    )
    _, raw_refresh = await _create_refresh_token(
        session, user_id=user.id, business_id=business_id, family_id=family_id
    )
    return IssuedSession(
        user=user,
        access_token=access_token,
        refresh_token_raw=raw_refresh,
        expires_in=settings.JWT_ACCESS_TTL_MINUTES * 60,
    )


async def _issue_pre_tenant(
    session: AsyncSession, *, user: User, memberships: list[tuple[Membership, Business]]
) -> IssuedSession:
    """Identity-only token: no tenant_id/role claim, so `get_tenant_context` 403s.

    Only good for /auth/me, /businesses/mine and /auth/select-business.
    """
    access_token = create_access_token(
        sub=user.id, tenant_id=None, role=None, platform_admin=user.is_platform_admin
    )
    _, raw_refresh = await _create_refresh_token(session, user_id=user.id, business_id=None)
    return IssuedSession(
        user=user,
        access_token=access_token,
        refresh_token_raw=raw_refresh,
        expires_in=settings.JWT_ACCESS_TTL_MINUTES * 60,
        requires_business_selection=True,
        memberships=memberships,
    )


async def signup(
    session: AsyncSession, *, email: str, password: str, business_name: str, vertical: str | None
) -> IssuedSession:
    """Create user + business + owner membership in one transaction, then log in.

    A single `commit()` at the end means a failure anywhere (duplicate
    email, slug collision) leaves no half-created tenant behind.
    """
    normalized_email = email.strip().lower()
    existing = (
        await session.execute(select(User.id).where(User.email == normalized_email))
    ).scalar_one_or_none()
    if existing is not None:
        raise AuthError("An account with that email already exists", status_code=409)

    user = User(
        id=uuid.uuid4(),
        email=normalized_email,
        password_hash=hash_password(password),
        is_platform_admin=False,
    )
    session.add(user)
    await session.flush()

    business, membership = await tenancy_service.create_business_with_owner(
        session, user_id=user.id, name=business_name, vertical=vertical
    )

    issued = await _issue_for_business(
        session, user=user, business_id=business.id, role=membership.role
    )
    try:
        await session.commit()
    except IntegrityError as exc:  # unique email / slug lost a race
        await session.rollback()
        raise AuthError("An account with that email already exists", status_code=409) from exc

    issued.memberships = [(membership, business)]
    return issued


async def login(session: AsyncSession, *, email: str, password: str) -> IssuedSession:
    """Verify credentials, then branch on membership count (see plan, Auth Flow).

    - exactly one membership -> tenant-scoped tokens immediately
    - zero or many          -> identity-only pre-tenant token; the client
                               must call select-business
    """
    normalized_email = email.strip().lower()
    user = (
        await session.execute(select(User).where(User.email == normalized_email))
    ).scalar_one_or_none()

    if user is None:
        verify_password(password, _dummy_password_hash())  # equalize timing
        raise AuthError("Invalid email or password")
    if not verify_password(password, user.password_hash):
        raise AuthError("Invalid email or password")

    memberships = await tenancy_service.list_memberships_for_user(session, user.id)
    active = [(m, b) for m, b in memberships if b.status == BusinessStatus.ACTIVE]

    if len(active) == 1:
        membership, business = active[0]
        await _revoke_active_tokens_for_business(
            session, user_id=user.id, business_id=business.id
        )
        issued = await _issue_for_business(
            session, user=user, business_id=business.id, role=membership.role
        )
        issued.memberships = active
    else:
        issued = await _issue_pre_tenant(session, user=user, memberships=active)

    await session.commit()
    return issued


async def select_business(
    session: AsyncSession, *, user: User, business_id: uuid.UUID
) -> IssuedSession:
    """Mint tenant-scoped tokens for a business the user is a member of."""
    membership = await tenancy_service.get_membership(
        session, user_id=user.id, business_id=business_id
    )
    if membership is None:
        raise AuthError("You are not a member of that business", status_code=403)

    business = await tenancy_service.get_business(session, business_id)
    if business is None or business.status != BusinessStatus.ACTIVE:
        raise AuthError("That business is not available", status_code=403)

    await _revoke_active_tokens_for_business(session, user_id=user.id, business_id=business_id)
    issued = await _issue_for_business(
        session, user=user, business_id=business_id, role=membership.role
    )
    issued.memberships = [(membership, business)]
    await session.commit()
    return issued


async def refresh(session: AsyncSession, *, raw_token: str) -> IssuedSession:
    """Validate + rotate a refresh token, with family revocation on reuse.

    Reuse detection: presenting a token that has already been rotated
    (`revoked_at IS NOT NULL`) means either an attacker replayed a stolen
    token or the legitimate client replayed one - either way the chain is
    considered compromised and the entire `family_id` is revoked, forcing a
    fresh login.
    """
    token_hash = hash_refresh_token(raw_token)
    row = (
        await session.execute(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
    ).scalar_one_or_none()

    if row is None:
        raise AuthError("Invalid refresh token")

    if row.revoked_at is not None:
        await _revoke_family(session, row.family_id)
        await session.commit()
        raise AuthError("Refresh token reuse detected; session family revoked")

    if row.expires_at <= datetime.now(timezone.utc):
        raise AuthError("Refresh token expired")

    user = await session.get(User, row.user_id)
    if user is None:
        raise AuthError("User no longer exists")

    role: MembershipRole | None = None
    memberships: list[tuple[Membership, Business]] = []
    if row.business_id is not None:
        membership = await tenancy_service.get_membership(
            session, user_id=user.id, business_id=row.business_id
        )
        if membership is None:
            # Membership was removed since the token was issued - drop the
            # whole family rather than silently downgrading to pre-tenant.
            await _revoke_family(session, row.family_id)
            await session.commit()
            raise AuthError("Membership revoked; please log in again", status_code=403)
        role = membership.role

    # Rotate: new token joins the same family, old one points at it.
    new_row, raw_new = await _create_refresh_token(
        session, user_id=user.id, business_id=row.business_id, family_id=row.family_id
    )
    row.revoked_at = datetime.now(timezone.utc)
    row.replaced_by_id = new_row.id

    if row.business_id is not None and role is not None:
        access_token = create_access_token(
            sub=user.id,
            tenant_id=row.business_id,
            role=role.value,
            platform_admin=user.is_platform_admin,
        )
        requires_selection = False
    else:
        memberships = await tenancy_service.list_memberships_for_user(session, user.id)
        access_token = create_access_token(
            sub=user.id, tenant_id=None, role=None, platform_admin=user.is_platform_admin
        )
        requires_selection = True

    await session.commit()
    return IssuedSession(
        user=user,
        access_token=access_token,
        refresh_token_raw=raw_new,
        expires_in=settings.JWT_ACCESS_TTL_MINUTES * 60,
        requires_business_selection=requires_selection,
        memberships=memberships,
    )


async def logout(session: AsyncSession, *, raw_token: str | None) -> None:
    """Revoke the presented refresh token. Idempotent and never errors.

    Only the presented token is revoked, not its family: rotation means
    at most one token per family is live, so this ends exactly this
    session while leaving other devices signed in.
    """
    if not raw_token:
        return
    await session.execute(
        update(RefreshToken)
        .where(
            RefreshToken.token_hash == hash_refresh_token(raw_token),
            RefreshToken.revoked_at.is_(None),
        )
        .values(revoked_at=datetime.now(timezone.utc))
    )
    await session.commit()
