"""Shared FastAPI dependencies: authentication, tenant context, authorization.

Dependency chain:

    get_token_payload   -> decoded, signature-verified JWT claims
    get_current_user    -> the `users` row for `sub` (401 if gone)
    get_tenant_context  -> requires a `tenant_id` claim, runs SET LOCAL,
                           returns TenantContext (403 if pre-tenant token)
    require_role(...)   -> get_tenant_context + role check
    require_platform_admin -> claim check AND a fresh DB read of
                           users.is_platform_admin
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Callable, Awaitable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.core.security import decode_access_token
from fusionflow.db.session import get_db_session, set_tenant_context
from fusionflow.modules.auth.models import User
from fusionflow.modules.tenancy.models import MembershipRole

# auto_error=False so a missing header produces our own 401 shape rather
# than FastAPI's default, and so optional-auth routes stay possible later.
bearer_scheme = HTTPBearer(auto_error=False, description="Bearer <access_token>")

SessionDep = Annotated[AsyncSession, Depends(get_db_session)]

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


@dataclass(frozen=True)
class TenantContext:
    """The resolved tenant scope of the current request."""

    tenant_id: uuid.UUID
    role: MembershipRole
    user: User


async def get_token_payload(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise _UNAUTHENTICATED
    try:
        return decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Access token expired",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


TokenPayloadDep = Annotated[dict[str, Any], Depends(get_token_payload)]


async def get_current_user(payload: TokenPayloadDep, session: SessionDep) -> User:
    """Load the `users` row named by the token's `sub` claim.

    The token is re-checked against the database on every request so a
    deleted user's still-valid JWT stops working immediately.
    """
    raw_sub = payload.get("sub")
    try:
        user_id = uuid.UUID(str(raw_sub))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token subject"
        ) from exc

    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def get_tenant_context(
    payload: TokenPayloadDep,
    user: CurrentUserDep,
    session: SessionDep,
) -> TenantContext:
    """Require a tenant-scoped token and bind the tenant to this transaction.

    Runs `SET LOCAL app.current_tenant_id` so every query issued by the
    handler is filtered by Postgres RLS. Any route touching tenant-scoped
    data must depend on this (directly or via `require_role`) - forgetting
    it returns empty result sets rather than an error, which is the
    failure mode called out as Risk #2 in the plan.
    """
    raw_tenant_id = payload.get("tenant_id")
    if not raw_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "No business selected for this session. "
                "Call POST /api/v1/auth/select-business first."
            ),
        )
    try:
        tenant_id = uuid.UUID(str(raw_tenant_id))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Malformed tenant_id claim"
        ) from exc

    raw_role = payload.get("role")
    try:
        role = MembershipRole(raw_role)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Malformed role claim"
        ) from exc

    await set_tenant_context(session, tenant_id)
    return TenantContext(tenant_id=tenant_id, role=role, user=user)


TenantContextDep = Annotated[TenantContext, Depends(get_tenant_context)]


def require_role(
    *roles: MembershipRole,
) -> Callable[[TenantContext], Awaitable[TenantContext]]:
    """Dependency factory: tenant context + membership-role allowlist.

    Usage: `ctx: TenantContext = Depends(require_role(MembershipRole.OWNER,
    MembershipRole.ADMIN))`.
    """
    if not roles:
        raise ValueError("require_role() needs at least one role")
    allowed = frozenset(roles)

    async def _dependency(context: TenantContextDep) -> TenantContext:
        if context.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "Insufficient role: requires one of "
                    f"{', '.join(sorted(r.value for r in allowed))}"
                ),
            )
        return context

    return _dependency


async def require_platform_admin(payload: TokenPayloadDep, session: SessionDep) -> User:
    """Gate for `/api/admin/*`. Verifies the claim AND the database flag.

    The JWT claim alone is never sufficient: a token minted before the flag
    was revoked would still carry `platform_admin: true` until it expires.
    Re-reading `users.is_platform_admin` makes revocation effective
    immediately, at the cost of one indexed primary-key lookup.
    """
    if payload.get("platform_admin") is not True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin privileges required"
        )

    raw_sub = payload.get("sub")
    try:
        user_id = uuid.UUID(str(raw_sub))
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token subject"
        ) from exc

    user = (
        await session.execute(select(User).where(User.id == user_id, User.is_platform_admin.is_(True)))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Platform admin privileges required"
        )
    return user
