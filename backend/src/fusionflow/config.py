from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central runtime configuration, read from environment variables / .env.

    None of the defaults here are production-safe - see .env.example for
    per-field notes (ENCRYPTION_KEY and JWT_SECRET in particular).
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENVIRONMENT: str = "development"

    DATABASE_URL: str = "postgresql+asyncpg://fusionflow:fusionflow@localhost:5432/fusionflow"

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
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    @property
    def is_development(self) -> bool:
        return self.ENVIRONMENT.lower() in {"development", "dev", "local", "test"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
