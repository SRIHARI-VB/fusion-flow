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

    # --- Google (Calendar / Gmail / Meet / Sheets) ---
    # One platform-level Google Cloud OAuth app shared by all four
    # connectors (they differ only in requested `scope`) - the registered
    # redirect_uri in Google Cloud Console must be
    # `{BACKEND_PUBLIC_BASE_URL}/api/v1/connectors/oauth/callback/<type_key>`
    # for each of google_calendar/gmail/google_meet/google_sheets, since
    # each connector type gets its own callback path (see router.py's
    # generic `/oauth/callback/{type_key}`) despite sharing one app.
    # Unset in dev by design - see connectors/google/oauth.py's stub-mode
    # fallback, mirroring whatsapp_configured below.
    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_OAUTH_AUTHORIZE_URL: str = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_OAUTH_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
    GOOGLE_OAUTH_REVOKE_URL: str = "https://oauth2.googleapis.com/revoke"
    GOOGLE_USERINFO_URL: str = "https://www.googleapis.com/oauth2/v2/userinfo"
    GOOGLE_CALENDAR_API_BASE_URL: str = "https://www.googleapis.com/calendar/v3"
    GMAIL_API_BASE_URL: str = "https://gmail.googleapis.com/gmail/v1"
    GOOGLE_MEET_API_BASE_URL: str = "https://meet.googleapis.com/v2"
    GOOGLE_SHEETS_API_BASE_URL: str = "https://sheets.googleapis.com/v4"

    # --- Instagram (Meta Graph API - Instagram Messaging) ---
    # `auth_mode="api_key"`, same BYO-credentials model as WhatsApp: each
    # tenant pastes their own IG professional account id + access token
    # (generated in their own Meta Business Suite) - no platform-level
    # Meta app id/secret needed for the connect step itself.
    INSTAGRAM_GRAPH_API_BASE_URL: str = "https://graph.facebook.com/v20.0"
    # App-level secret used to verify X-Hub-Signature-256 on inbound
    # webhooks, when a tenant doesn't supply their own `app_secret` at
    # connect time - mirrors WHATSAPP_WEBHOOK_APP_SECRET exactly.
    INSTAGRAM_WEBHOOK_APP_SECRET: str | None = None
    # Fallback verify token for the GET webhook handshake, used only when
    # no connected instance's own stored `webhook_verify_token` matches -
    # see instagram/adapter.py's module docstring for why a per-tenant
    # value is honored here (unlike WhatsApp's single global token).
    INSTAGRAM_WEBHOOK_VERIFY_TOKEN: str = "dev-only-instagram-verify-token"

    # --- Telegram (Bot API) ---
    # `auth_mode="api_key"`: each tenant brings their own bot, created via
    # @BotFather in their own Telegram account - no platform-level Telegram
    # app/credentials exist or are needed. Unlike Meta's webhook model
    # (one shared callback URL, tenant identified from payload content),
    # Telegram's `setWebhook` call lets *us* choose the callback URL per
    # bot - `telegram/adapter.py` registers
    # `{BACKEND_PUBLIC_BASE_URL}/api/v1/webhooks/telegram?instance_id=<uuid>`
    # for every connect, reusing the same `?instance_id=` query-param
    # resolution convention `razorpay/adapter.py::resolve_instance_for_webhook`
    # already established (there, it's a fallback for a manually-pasted
    # URL; here, since we control registration, it's the sole and always-
    # present mechanism - no brute-force fallback needed).
    TELEGRAM_BOT_API_BASE_URL: str = "https://api.telegram.org"
    # Fallback used only when a connected instance didn't supply its own
    # `webhook_secret_token` at connect time - mirrors
    # INSTAGRAM_WEBHOOK_APP_SECRET's per-instance-then-global convention.
    TELEGRAM_WEBHOOK_SECRET_TOKEN: str | None = None

    # --- Facebook (Meta Graph API - Page Messenger) ---
    # `auth_mode="api_key"`, identical BYO-credentials model to
    # `whatsapp`/`instagram`: each tenant pastes their own Facebook Page id
    # + Page access token (generated in their own Meta Business Suite) -
    # no platform-level Meta app id/secret needed for the connect step.
    FACEBOOK_GRAPH_API_BASE_URL: str = "https://graph.facebook.com/v20.0"
    # App-level secret used to verify X-Hub-Signature-256 on inbound
    # webhooks, when a tenant doesn't supply their own `app_secret` at
    # connect time - mirrors WHATSAPP_WEBHOOK_APP_SECRET/
    # INSTAGRAM_WEBHOOK_APP_SECRET exactly.
    FACEBOOK_WEBHOOK_APP_SECRET: str | None = None
    # Fallback verify token for the GET webhook handshake - mirrors
    # WHATSAPP_WEBHOOK_VERIFY_TOKEN (one fixed value for every tenant;
    # Meta's handshake carries no tenant identifier at all).
    FACEBOOK_WEBHOOK_VERIFY_TOKEN: str = "dev-only-facebook-verify-token"

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

    @property
    def google_configured(self) -> bool:
        """True only when a real Google Cloud OAuth app is configured.

        Drives the stub-vs-real fork in connectors/google/oauth.py, shared
        by all four Google connectors.
        """
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)


@lru_cache
def get_connector_settings() -> ConnectorSettings:
    return ConnectorSettings()
