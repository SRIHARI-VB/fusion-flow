"""Connector-module-local settings.

Kept separate from the shared `fusionflow.config.Settings` deliberately:
this module's ownership boundary (see the task that created it) is
`modules/connectors/**` only, so provider credentials/URLs live in their
own `pydantic-settings` model that reads the same `.env` file rather than
adding fields to the central `Settings` class. `extra="ignore"` on both
means this can be merged into the central class later with no behavior
change - it is just a namespacing choice today.

Every field here is optional/has a dev-safe default, so importing this
module never requires real Meta/Razorpay credentials to be configured.
Feature/adapter code detects "no real credentials configured" and falls
back to a clearly-logged stub path - see whatsapp/adapter.py and
razorpay/adapter.py.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ConnectorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- WhatsApp (Meta Graph API / Embedded Signup) ---
    # Unset in dev by design - see whatsapp/adapter.py's stub-mode fallback.
    WHATSAPP_APP_ID: str | None = None
    WHATSAPP_APP_SECRET: str | None = None
    # App-level secret used to verify X-Hub-Signature-256 on inbound
    # webhooks (Meta signs with the App Secret, not a per-WABA secret).
    WHATSAPP_WEBHOOK_APP_SECRET: str | None = None
    # Token Meta echoes back during the one-time GET webhook subscription
    # handshake (hub.verify_token).
    WHATSAPP_WEBHOOK_VERIFY_TOKEN: str = "dev-only-whatsapp-verify-token"
    WHATSAPP_GRAPH_API_BASE_URL: str = "https://graph.facebook.com/v20.0"
    WHATSAPP_OAUTH_DIALOG_URL: str = "https://www.facebook.com/v20.0/dialog/oauth"

    # --- Razorpay ---
    RAZORPAY_API_BASE_URL: str = "https://api.razorpay.com/v1"
    # Fallback webhook secret used only when a webhook arrives without an
    # `instance_id` query param and no connected instance's own stored
    # secret verifies it - see razorpay/adapter.py + webhooks.py for the
    # documented tradeoff.
    RAZORPAY_WEBHOOK_SECRET: str | None = None

    # Backend's own public base URL, used to build the OAuth redirect_uri
    # Meta calls back into (must be registered in the Meta app dashboard).
    BACKEND_PUBLIC_BASE_URL: str = "http://localhost:8000"
    # Where the browser is sent after an OAuth callback completes/fails.
    FRONTEND_BASE_URL: str = "http://localhost:5173"

    OAUTH_STATE_TTL_MINUTES: int = 10

    @property
    def whatsapp_configured(self) -> bool:
        """True only when real Meta app credentials are present.

        Drives the stub-vs-real fork in whatsapp/adapter.py - see its
        module docstring.
        """
        return bool(self.WHATSAPP_APP_ID and self.WHATSAPP_APP_SECRET)


@lru_cache
def get_connector_settings() -> ConnectorSettings:
    return ConnectorSettings()
