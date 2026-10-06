"""Generic audit logging for every `/api/admin/*` request.

Implemented as a custom `fastapi.routing.APIRoute` subclass rather than an
app-level Starlette middleware, so the whole concern stays self-contained
inside `modules/admin` - the router that mounts under `/api/admin` (see
`router.py`) just passes `route_class=AuditLoggingRoute` to its
`APIRouter(...)` constructor, and nothing in `main.py` has to know this
exists.

One `AuditLog` row is written per completed request (success or error),
after the handler has run, using a *fresh* DB session rather than the
request's own request-scoped session - by the time `custom_handler` below
runs, the request's own session dependency may already have been closed by
FastAPI's dependency-teardown, and audit logging must never be the thing
that makes an otherwise-successful admin action fail.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Coroutine

import jwt as pyjwt
from fastapi import Request, Response
from fastapi.routing import APIRoute

from fusionflow.config import get_settings
from fusionflow.core.security import JWT_ALGORITHM
from fusionflow.db.session import async_session_factory
from fusionflow.modules.admin.models import AuditLog

logger = logging.getLogger(__name__)

# "/api/admin/tenants/{id}" -> ["api", "admin", "tenants", "<id>"]; index 2 is
# the first segment that names *this module's* resource collection.
_TARGET_TYPE_SEGMENT_INDEX = 2


def _decoded_claims(request: Request) -> dict[str, Any] | None:
    """Independently re-verify the bearer token's signature.

    `require_platform_admin` already did this for the handler itself, but
    this runs as a separate concern (a route wrapper, not a dependency) and
    must not trust an unverified/forged token for who gets attributed in the
    audit trail.
    """
    header = request.headers.get("authorization")
    if not header or not header.lower().startswith("bearer "):
        return None
    token = header.split(" ", 1)[1].strip()
    try:
        return pyjwt.decode(token, get_settings().JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except pyjwt.PyJWTError:
        return None


def _target_from_path(request: Request) -> tuple[str | None, str | None]:
    segments = [s for s in request.url.path.split("/") if s]
    target_type = (
        segments[_TARGET_TYPE_SEGMENT_INDEX] if len(segments) > _TARGET_TYPE_SEGMENT_INDEX else None
    )
    # Phase-1 admin routes have at most one path param per route
    # ({business_id} / {flag_id} / ...); good enough for a generic logger.
    target_id = next(iter(request.path_params.values()), None)
    return target_type, (str(target_id) if target_id is not None else None)


async def _write_audit_log(request: Request, status_code: int) -> None:
    claims = _decoded_claims(request)
    if not claims or not claims.get("sub"):
        # No verifiable actor (missing/malformed/expired token) - there is
        # nothing safe to attribute the row to, so skip rather than write a
        # misleading one. Requests that get this far without a valid token
        # were going to be rejected with 401/403 by `require_platform_admin`
        # anyway.
        return
    try:
        actor_user_id = uuid.UUID(str(claims["sub"]))
    except (TypeError, ValueError):
        return

    target_type, target_id = _target_from_path(request)
    tenant_id: uuid.UUID | None = None
    if target_type == "tenants" and target_id:
        try:
            tenant_id = uuid.UUID(target_id)
        except ValueError:
            tenant_id = None

    row = AuditLog(
        id=uuid.uuid4(),
        actor_user_id=actor_user_id,
        actor_is_platform_admin=bool(claims.get("platform_admin")),
        tenant_id=tenant_id,
        action=f"{request.method} {request.url.path}",
        target_type=target_type,
        target_id=target_id,
        extra_metadata={
            "status_code": status_code,
            "query": dict(request.query_params),
            # Handlers may stash details (e.g. override reason) here.
            **(getattr(request.state, "audit_extra", None) or {}),
        },
        ip_address=request.client.host if request.client else None,
    )
    try:
        async with async_session_factory() as session:
            session.add(row)
            await session.commit()
    except Exception:  # noqa: BLE001 - defensive: logging must never break the actual admin action
        logger.exception(
            "Failed to write admin audit log row for %s %s", request.method, request.url.path
        )


class AuditLoggingRoute(APIRoute):
    """Route class that writes one `AuditLog` row per completed request."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original_handler = super().get_route_handler()

        async def custom_handler(request: Request) -> Response:
            status_code = 500
            try:
                response = await original_handler(request)
                status_code = response.status_code
                return response
            except Exception as exc:
                status_code = getattr(exc, "status_code", 500)
                raise
            finally:
                await _write_audit_log(request, status_code)

        return custom_handler
