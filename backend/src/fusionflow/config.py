import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central runtime configuration, read from environment variables / .env.

    None of the defaults here are production-safe - see .env.example for
    per-field notes (ENCRYPTION_KEY and JWT_SECRET in particular).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = "development"

    # Shared secret for `/api/v1/internal/scheduled-tasks` (the Vercel
    # Cron-triggered sweep that resumes `flow.delay` waits and fires due
    # `WorkflowSchedule`s - see that route's docstring for why this exists
    # at all: neither can rely on a webhook to piggyback on when running
    # serverless). Vercel automatically sends
    # `Authorization: Bearer <this value>` for a configured cron job (see
    # `vercel.json`). Unset (the local-dev default) means the endpoint is
    # open with a logged warning - never leave it unset in production.
    CRON_SECRET: str | None = None

    # Migration/owner-role connection: alembic (alembic/env.py) always uses
    # this one, and it is the fallback for RUNTIME_DATABASE_URL below when
    # that is unset (fine for a simple local Postgres where the connecting
    # role already is low-privilege). It must NOT be what the running app
    # uses in any environment where this role has elevated rights - see
    # RUNTIME_DATABASE_URL.
    DATABASE_URL: str = "postgresql+asyncpg://fusionflow:fusionflow@localhost:5432/fusionflow"

    # The role the *running app* queries as (db/session.py's engine, never
    # alembic). Must be a dedicated non-superuser, non-BYPASSRLS role for
    # RLS to actually apply - confirmed live against Supabase 2026-09-09
    # that its default `postgres` role is NOT a superuser but DOES have
    # `rolbypassrls = true`, which bypasses every tenant_isolation policy
    # just as completely. Optional: falls back to DATABASE_URL so a local
    # dev Postgres with one low-privilege role for everything still works
    # with a single URL.
    RUNTIME_DATABASE_URL: str | None = None

    # >= 32 bytes, as RFC 7518 s3.2 requires for HS256. Dev-only value.
    JWT_SECRET: str = "dev-only-change-me-jwt-secret-0123456789abcdef"
    JWT_ACCESS_TTL_MINUTES: int = 15
    JWT_REFRESH_TTL_DAYS: int = 30

    REDIS_ENABLED: bool = False
    REDIS_URL: str = "redis://localhost:6379/0"

    # false -> InProcessAsyncQueue (asyncio tasks, no broker needed).
    # true would select CeleryQueue, which is not wired yet and raises.
    BACKGROUND_JOBS_ENABLED: bool = False

    AI_ENABLED: bool = False

    # Dev-only symmetric key for core/encryption.py. NOT prod-safe - see
    # .env.example. Real deployments must inject this from a secret
    # manager / KMS and plan to rotate via encryption_key_version.
    ENCRYPTION_KEY: str = "Ua2yuHtia0s-2FhOZ4pQmyoVoFYIP5wsE7mYNzOD3Vw="

    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:5174"

    @property
    def runtime_database_url(self) -> str:
        return self.RUNTIME_DATABASE_URL or self.DATABASE_URL

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() in {"development", "dev", "local", "test"}

    @property
    def is_serverless(self) -> bool:
        """True when running as a Vercel Python function.

        Vercel sets `VERCEL=1` on every deployment (production, preview,
        and `vercel dev`) - used to skip the in-process "forever" pollers
        (see main.py's lifespan), which cannot run inside a per-request
        serverless invocation: each cold start would spin up a fresh
        polling loop that never gets a chance to actually poll on a
        useful cadence, while still opening its own DB connections every
        time it's resumed - exactly the kind of connection churn that
        exhausts a pooler's client slots under concurrent invocations.
        """
        return os.environ.get("VERCEL") == "1"


_DEV_ONLY_JWT_SECRET = "dev-only-change-me-jwt-secret-0123456789abcdef"
_DEV_ONLY_ENCRYPTION_KEY = "Ua2yuHtia0s-2FhOZ4pQmyoVoFYIP5wsE7mYNzOD3Vw="


class InsecureProductionConfigError(RuntimeError):
    """Raised at startup when a non-development deployment still has a
    dev-only secret default in effect. Both `JWT_SECRET` and
    `ENCRYPTION_KEY` were, until this check existed, silently usable in
    production if an operator forgot to set the real env var - refusing to
    boot is much safer than an admin/JWT-forging or credential-decryption
    hole that only shows up in an audit."""


def validate_secrets_for_environment(settings: Settings) -> None:
    if settings.is_development:
        return
    if settings.JWT_SECRET == _DEV_ONLY_JWT_SECRET:
        raise InsecureProductionConfigError(
            "JWT_SECRET is still the dev-only default outside a development ENVIRONMENT - set a real secret."
        )
    if settings.ENCRYPTION_KEY == _DEV_ONLY_ENCRYPTION_KEY:
        raise InsecureProductionConfigError(
            "ENCRYPTION_KEY is still the dev-only default outside a development ENVIRONMENT - set a real secret."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
