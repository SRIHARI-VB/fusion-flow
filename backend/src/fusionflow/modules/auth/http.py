"""HTTP-layer helpers shared by the auth and tenancy routers.

Kept out of `auth/router.py` so `tenancy/router.py` (which also mints
tokens, via `POST /businesses/{id}/switch`) does not have to import from
another module's router.
"""

from __future__ import annotations

from fastapi import Response

from fusionflow.config import get_settings
from fusionflow.modules.auth.schemas import TokenResponse, UserOut
from fusionflow.modules.auth.service import IssuedSession
from fusionflow.modules.tenancy.service import to_business_membership_out

settings = get_settings()

REFRESH_COOKIE_NAME = "fusionflow_refresh"
# Path-scoped so the cookie is only ever sent to the endpoints that need
# it, instead of riding along on every API call.
REFRESH_COOKIE_PATH = "/api/v1"


def set_refresh_cookie(response: Response, raw_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_token,
        max_age=settings.JWT_REFRESH_TTL_DAYS * 24 * 3600,
        httponly=True,
        # Secure is relaxed in dev only, so the cookie still works over
        # plain http://localhost; every other environment gets Secure.
        secure=not settings.is_development,
        # "strict" in dev (frontend/backend are both on `localhost`, just
        # different ports - same-site, so strict costs nothing there).
        # "none" in every other environment: frontend and backend are
        # deployed as two separate `*.vercel.app` projects, which the
        # browser treats as different SITES (vercel.app is on the Public
        # Suffix List) - a "strict" (or even "lax") cookie is silently
        # withheld on every cross-site fetch/XHR AND on a top-level
        # navigation returning from a third party (e.g. Google's OAuth
        # consent redirect back to the frontend), breaking session
        # restore on reload and stranding the OAuth-connect flow at
        # /login. "none" requires Secure=True (already true whenever
        # this branch is reached, since is_development is false).
        samesite="strict" if settings.is_development else "none",
        path=REFRESH_COOKIE_PATH,
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)


def to_token_response(issued: IssuedSession) -> TokenResponse:
    return TokenResponse(
        access_token=issued.access_token,
        expires_in=issued.expires_in,
        refresh_token=issued.refresh_token_raw,
        requires_business_selection=issued.requires_business_selection,
        user=UserOut.model_validate(issued.user),
        businesses=[to_business_membership_out(m, b) for m, b in issued.memberships],
    )
