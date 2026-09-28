import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from fusionflow.config import get_settings

settings = get_settings()

_hasher = PasswordHasher()

JWT_ALGORITHM = "HS256"


def hash_password(plain_password: str) -> str:
    return _hasher.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, plain_password)
    except VerifyMismatchError:
        return False


def create_access_token(
    *,
    sub: uuid.UUID,
    tenant_id: uuid.UUID | None = None,
    role: str | None = None,
    platform_admin: bool = False,
    ttl_minutes: int | None = None,
) -> str:
    """Mint an access token with the platform's fixed claim shape.

    Claim shape (stable contract other modules depend on):
      sub               - user id (str uuid)
      tenant_id         - business id (str uuid) or None for a pre-tenant /
                          platform-admin-only token
      role              - membership role for `tenant_id`, or None
      jti               - unique token id, used for auditing/allowing
                          future access-token revocation lists
      platform_admin    - bool, true only for platform-admin tokens
      iat / exp         - standard JWT timestamp claims
    """
    now = datetime.now(timezone.utc)
    ttl = timedelta(minutes=ttl_minutes if ttl_minutes is not None else settings.JWT_ACCESS_TTL_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(sub),
        "tenant_id": str(tenant_id) if tenant_id else None,
        "role": role,
        "jti": str(uuid.uuid4()),
        "platform_admin": platform_admin,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode + validate an access token. Raises jwt.PyJWTError subclasses on failure."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALGORITHM])


def generate_refresh_token() -> tuple[str, str]:
    """Generate an opaque refresh token.

    Returns (raw_token, sha256_hex_hash). Only the hash is ever persisted;
    the raw value is handed to the client once and is not recoverable
    from the database.
    """
    raw = secrets.token_urlsafe(32)  # 256 bits of entropy
    return raw, hash_refresh_token(raw)


def hash_refresh_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def refresh_token_expiry() -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=settings.JWT_REFRESH_TTL_DAYS)


STEP_UP_TTL_MINUTES = 45


def create_step_up_token(*, sub: uuid.UUID) -> tuple[str, datetime]:
    """A short-lived, self-contained "I re-entered my password just now"
    proof - deliberately NOT a DB-backed session row: this only ever needs
    to answer "is this still fresh enough," which a signed, short-TTL JWT
    (reusing the same `JWT_SECRET`/algorithm the main access token already
    uses, no new secret to manage) answers without a round trip. Distinct
    claim shape from `create_access_token` (no tenant/role claims at all)
    so it can never be mistaken for, or substituted as, a real access
    token by anything that decodes it - `decode_step_up_token` also
    explicitly checks the `step_up` marker claim for the same reason.
    """
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=STEP_UP_TTL_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(sub),
        "step_up": True,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    token = jwt.encode(payload, settings.JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expires_at


def decode_step_up_token(token: str) -> uuid.UUID:
    """Raises `jwt.PyJWTError` (expired/malformed/bad signature) or
    `ValueError` (well-formed JWT, but not actually a step-up token) -
    callers should treat both as "no valid step-up," not distinguish them."""
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[JWT_ALGORITHM])
    if payload.get("step_up") is not True:
        raise ValueError("token is not a step-up token")
    return uuid.UUID(str(payload["sub"]))
