"""Offline unit tests for the core primitives: security, encryption, cache, jobs.

None of these need Postgres, Redis or Celery.
"""

from __future__ import annotations

import asyncio
import uuid

import jwt
import pytest

from fusionflow.config import Settings
from fusionflow.core.cache import InMemoryCacheBackend, get_cache_backend
from fusionflow.core.encryption import decrypt_secret, encrypt_secret, redact_preview
from fusionflow.core.jobs import CeleryQueue, InProcessAsyncQueue, get_job_queue
from fusionflow.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

# --------------------------------------------------------------------------
# core/security.py
# --------------------------------------------------------------------------


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert hashed.startswith("$argon2")
    assert verify_password("correct horse battery staple", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_access_token_carries_the_documented_claim_shape() -> None:
    user_id, tenant_id = uuid.uuid4(), uuid.uuid4()
    claims = decode_access_token(
        create_access_token(sub=user_id, tenant_id=tenant_id, role="owner")
    )
    assert claims["sub"] == str(user_id)
    assert claims["tenant_id"] == str(tenant_id)
    assert claims["role"] == "owner"
    assert claims["platform_admin"] is False
    assert uuid.UUID(claims["jti"])
    assert claims["exp"] > claims["iat"]


def test_pre_tenant_token_omits_tenant_and_role() -> None:
    claims = decode_access_token(create_access_token(sub=uuid.uuid4()))
    assert claims["tenant_id"] is None
    assert claims["role"] is None
    assert claims["platform_admin"] is False


def test_platform_admin_token_sets_the_flag_and_no_tenant() -> None:
    claims = decode_access_token(create_access_token(sub=uuid.uuid4(), platform_admin=True))
    assert claims["platform_admin"] is True
    assert claims["tenant_id"] is None


def test_expired_token_is_rejected() -> None:
    token = create_access_token(sub=uuid.uuid4(), ttl_minutes=-1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token_is_rejected() -> None:
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(create_access_token(sub=uuid.uuid4()) + "tampered")


def test_refresh_token_is_opaque_and_only_its_hash_is_storable() -> None:
    raw, digest = generate_refresh_token()
    assert raw != digest
    assert len(digest) == 64
    assert hash_refresh_token(raw) == digest

    raw2, digest2 = generate_refresh_token()
    assert raw != raw2 and digest != digest2  # 256 bits of entropy


# --------------------------------------------------------------------------
# core/encryption.py
# --------------------------------------------------------------------------


def test_encryption_roundtrip() -> None:
    secret = "rzp_test_1234567890ABCD"
    ciphertext = encrypt_secret(secret)
    assert isinstance(ciphertext, bytes)
    assert secret.encode() not in ciphertext
    assert decrypt_secret(ciphertext) == secret


def test_decrypt_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        decrypt_secret(b"not-a-real-fernet-token")


def test_unknown_key_version_is_an_explicit_error() -> None:
    """Guards the future KMS rotation path (see encryption_key_version)."""
    with pytest.raises(NotImplementedError):
        encrypt_secret("x", key_version=99)


def test_redact_preview_keeps_first_3_and_last_4() -> None:
    secret = "sk_live_1234567890"
    preview = redact_preview(secret)
    assert preview.startswith("sk_")
    assert preview.endswith("7890")
    assert len(preview) == len(secret)
    assert secret[3:-4] not in preview


@pytest.mark.parametrize("value", ["", "a", "abcdefg"])
def test_redact_preview_fully_masks_short_secrets(value: str) -> None:
    assert redact_preview(value) == "*" * len(value)


# --------------------------------------------------------------------------
# core/cache.py
# --------------------------------------------------------------------------


async def test_in_memory_cache_get_set_delete_incr() -> None:
    cache = InMemoryCacheBackend()
    assert await cache.get("missing") is None

    await cache.set("k", "v")
    assert await cache.get("k") == "v"

    await cache.delete("k")
    assert await cache.get("k") is None

    assert await cache.incr("counter") == 1
    assert await cache.incr("counter", 5) == 6


async def test_in_memory_cache_expires_lazily() -> None:
    cache = InMemoryCacheBackend()
    await cache.set("k", "v", ttl_seconds=0)
    assert await cache.get("k") is None


def test_cache_factory_returns_in_memory_backend_when_redis_disabled() -> None:
    assert isinstance(get_cache_backend(Settings(REDIS_ENABLED=False)), InMemoryCacheBackend)


# --------------------------------------------------------------------------
# core/jobs.py
# --------------------------------------------------------------------------


async def test_in_process_queue_runs_handlers() -> None:
    queue = InProcessAsyncQueue()
    seen: list[dict] = []

    async def handler(**kwargs: object) -> None:
        seen.append(kwargs)

    queue.register_handler("greet", handler)
    await queue.enqueue("greet", name="ada")
    await asyncio.wait_for(queue.drain(), timeout=5)

    assert seen == [{"name": "ada"}]


async def test_in_process_queue_retries_then_succeeds() -> None:
    queue = InProcessAsyncQueue(max_retries=3, retry_delay_seconds=0)
    attempts: list[int] = []

    async def flaky(n: int) -> None:
        attempts.append(n)
        if len(attempts) < 2:
            raise RuntimeError("transient")

    queue.register_handler("flaky", flaky)
    await queue.enqueue("flaky", n=7)
    await asyncio.wait_for(queue.drain(), timeout=5)

    assert attempts == [7, 7]


async def test_in_process_queue_gives_up_after_max_retries() -> None:
    queue = InProcessAsyncQueue(max_retries=2, retry_delay_seconds=0)
    attempts: list[int] = []

    async def always_fails() -> None:
        attempts.append(1)
        raise RuntimeError("boom")

    queue.register_handler("bad", always_fails)
    await queue.enqueue("bad")
    await asyncio.wait_for(queue.drain(), timeout=5)

    assert len(attempts) == 2


async def test_in_process_queue_rejects_unknown_jobs() -> None:
    with pytest.raises(KeyError):
        await InProcessAsyncQueue().enqueue("nope")


def test_job_factory_returns_in_process_queue_by_default() -> None:
    assert isinstance(get_job_queue(Settings(BACKGROUND_JOBS_ENABLED=False)), InProcessAsyncQueue)


def test_celery_queue_is_an_unwired_stub() -> None:
    with pytest.raises(NotImplementedError, match="BACKGROUND_JOBS_ENABLED=false"):
        CeleryQueue()
