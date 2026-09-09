"""Cache abstraction — "provision but skip in dev".

Calling code depends only on the `CacheBackend` protocol; nothing outside
this module ever imports `redis`. `get_cache_backend(settings)` picks the
implementation once, driven by `REDIS_ENABLED`, so a dev machine with no
Redis (and without the `redis` package installed at all) boots normally.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from fusionflow.config import Settings


@runtime_checkable
class CacheBackend(Protocol):
    """Minimal async cache surface shared by every backend."""

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def incr(self, key: str, amount: int = 1) -> int: ...


class InMemoryCacheBackend:
    """Process-local cache. Default in dev, and the only backend used by tests.

    Deliberately simple: a dict guarded by an asyncio.Lock with lazy TTL
    expiry (entries are evicted when read after expiry, not by a sweeper
    task). Values are process-local, so this is not usable across multiple
    workers - which is exactly why prod flips `REDIS_ENABLED=true`.
    """

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}
        self._lock = asyncio.Lock()

    @staticmethod
    def _expiry(ttl_seconds: int | None) -> float | None:
        return time.monotonic() + ttl_seconds if ttl_seconds is not None else None

    def _is_expired(self, expires_at: float | None) -> bool:
        return expires_at is not None and time.monotonic() >= expires_at

    async def get(self, key: str) -> str | None:
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if self._is_expired(expires_at):
                # Lazy expiry: drop on read rather than running a sweeper.
                del self._store[key]
                return None
            return value

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        async with self._lock:
            self._store[key] = (value, self._expiry(ttl_seconds))

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._store.pop(key, None)

    async def incr(self, key: str, amount: int = 1) -> int:
        async with self._lock:
            entry = self._store.get(key)
            current = 0
            expires_at: float | None = None
            if entry is not None and not self._is_expired(entry[1]):
                current = int(entry[0])
                expires_at = entry[1]  # incr must not extend an existing TTL
            new_value = current + amount
            self._store[key] = (str(new_value), expires_at)
            return new_value


class RedisCacheBackend:
    """Redis-backed cache, used only when `REDIS_ENABLED=true`.

    `redis.asyncio` is imported inside `__init__` (never at module import
    time) so importing this module - which `main.py` does on every boot -
    cannot fail when the optional `redis` package is not installed.
    Install it with the `redis` extra: `pip install -e ".[redis]"`.
    """

    def __init__(self, redis_url: str) -> None:
        try:
            import redis.asyncio as redis_asyncio  # noqa: PLC0415 - intentionally deferred
        except ImportError as exc:  # pragma: no cover - depends on install extras
            raise RuntimeError(
                "REDIS_ENABLED=true but the 'redis' package is not installed. "
                'Install the optional extra: pip install -e ".[redis]" '
                "(or set REDIS_ENABLED=false to use InMemoryCacheBackend)."
            ) from exc

        self._client: Any = redis_asyncio.from_url(redis_url, decode_responses=True)

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        await self._client.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._client.delete(key)

    async def incr(self, key: str, amount: int = 1) -> int:
        return int(await self._client.incrby(key, amount))

    async def aclose(self) -> None:
        await self._client.aclose()


def get_cache_backend(settings: Settings) -> CacheBackend:
    """Select the cache backend once, at startup, from configuration."""
    if settings.REDIS_ENABLED:
        return RedisCacheBackend(settings.REDIS_URL)
    return InMemoryCacheBackend()
