"""`ConnectorAdapter` ABC + `ConnectorRegistry`.

Per the plan's "Connector Lifecycle Framework": one adapter implementation
per provider (WhatsApp, Razorpay in phase 1), registered by
`connector_type_key` into the module-level `ConnectorRegistry`. Everything
in `service.py` and `router.py` calls through this interface only - zero
provider branching in generic code. Provider quirks (Meta's OAuth dance,
Razorpay's api-key model, each one's webhook signature scheme) live
entirely inside the adapter subclass.

Secret redaction guarantee (plan): adapters populate `connected_identity`
via an explicit safe-field allowlist they construct themselves; the raw
provider payload is never stored there. `connector_credentials` is
decrypted only inside adapter code making an outbound provider call
(typically via `service.get_credential_secret`), never in a route handler
building a response DTO.
"""

from __future__ import annotations

import abc
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Mapping

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids import cycles at runtime
    from sqlalchemy.ext.asyncio import AsyncSession

    from fusionflow.modules.connectors.models import (
        ConnectorEvent,
        ConnectorInstance,
        ConnectorOAuthState,
    )
    from fusionflow.modules.connectors.models import HealthStatus

AuthMode = Literal["oauth", "api_key"]


@dataclass
class ConnectResult:
    """Outcome of `ConnectorAdapter.initiate_connect`.

    - `auth_mode="oauth"` adapters: set `redirect_url` (the router 302s
      the browser there); the instance is left in `connecting` until
      `handle_oauth_callback` lands.
    - `auth_mode="api_key"` adapters: validate synchronously and return
      the final state/identity in this same call - `redirect_url` stays
      None.
    """

    state: "ConnectorState"  # noqa: F821 - see models.ConnectorState, avoided to dodge the cycle
    redirect_url: str | None = None
    connected_identity: dict[str, Any] = field(default_factory=dict)
    provider_ref_ids: dict[str, Any] = field(default_factory=dict)
    health_status: "HealthStatus | None" = None
    error_message: str | None = None


@dataclass
class HealthResult:
    """Outcome of `ConnectorAdapter.test_connection`."""

    health_status: "HealthStatus"
    detail: str | None = None
    connected_identity: dict[str, Any] | None = None


class ConnectorAdapter(abc.ABC):
    """One implementation per provider. See module docstring."""

    #: Matches `connector_types.key` this adapter serves.
    connector_type_key: str
    auth_mode: AuthMode
    #: JSON-schema-shaped dict describing `initiate_connect`'s `params`.
    config_schema: dict[str, Any] = {}

    @abc.abstractmethod
    async def initiate_connect(
        self,
        *,
        tenant_id: uuid.UUID,
        instance: "ConnectorInstance",
        params: dict[str, Any],
        session: "AsyncSession",
    ) -> ConnectResult:
        """Start (or, for api_key providers, complete) a connection.

        `instance` already exists in state `connecting` by the time this
        is called - see `service.connect`. Must not commit; the caller
        owns the transaction boundary.
        """

    async def handle_oauth_callback(
        self,
        *,
        oauth_state: "ConnectorOAuthState",
        code: str,
        instance: "ConnectorInstance",
        session: "AsyncSession",
    ) -> ConnectResult:
        """Complete an OAuth flow. Only required for `auth_mode="oauth"`."""
        raise NotImplementedError(f"{self.connector_type_key} does not support OAuth callbacks")

    @abc.abstractmethod
    async def test_connection(
        self, *, instance: "ConnectorInstance", session: "AsyncSession"
    ) -> HealthResult:
        """Best-effort live health check against the provider."""

    @abc.abstractmethod
    async def disconnect(self, *, instance: "ConnectorInstance", session: "AsyncSession") -> None:
        """Provider-side cleanup only (e.g. unsubscribe a webhook app).

        State transition to `disconnected` + `disconnected_at` stamping is
        generic and handled by `service.disconnect` - this hook is for
        whatever the provider needs done on its side, best-effort. Must
        not raise for "already disconnected on the provider's end".
        """

    @abc.abstractmethod
    def verify_webhook_signature(self, *, raw_payload: bytes, headers: Mapping[str, str]) -> bool:
        """Verify the provider's HMAC signature header over the raw body."""

    @abc.abstractmethod
    async def resolve_instance_for_webhook(
        self, *, raw_payload: bytes, headers: Mapping[str, str], query_params: Mapping[str, str], session: "AsyncSession"
    ) -> "ConnectorInstance | None":
        """Identify which tenant's instance an inbound webhook belongs to.

        Runs before any tenant context exists (the request is
        unauthenticated - only signature-verified), so this necessarily
        performs a cross-tenant lookup. See webhooks.py's module
        docstring for the RLS implication this has in production.
        """

    @abc.abstractmethod
    async def handle_webhook(
        self,
        *,
        instance: "ConnectorInstance",
        raw_payload: bytes,
        headers: Mapping[str, str],
        session: "AsyncSession",
    ) -> list["ConnectorEvent"]:
        """Parse a verified webhook body into `ConnectorEvent` row(s).

        Must not commit and must not touch `instance.last_webhook_at`
        (webhooks.py bumps that generically after this returns) - keeps
        provider parsing and generic bookkeeping separate.
        """

    async def perform_action(
        self, *, action: str, params: dict[str, Any], instance: "ConnectorInstance", session: "AsyncSession"
    ) -> dict[str, Any]:
        """Dispatch one named, provider-specific capability - the hook the
        workflow engine's generic `connector.action` node type (see
        `modules/workflows/nodes/connector_action.py`) calls through so a
        *new* capability on an *already-adapted* provider (e.g. "send a
        WhatsApp template message" alongside today's "send text") is one
        `elif action == "..."` branch added to the adapter's own override
        of this method, not a new `NodeExecutor` subclass, a new registry
        entry, or any workflow-engine code change at all.

        Default raises `NotImplementedError` - only adapters that actually
        expose actions to the workflow engine override this (today: only
        WhatsApp's `send_text_message`). Not `abc.abstractmethod`: Razorpay
        (and any future adapter with nothing meaningful to expose here)
        should not be forced to implement a no-op.
        """
        raise NotImplementedError(f"{self.connector_type_key} does not support action {action!r}")


class ConnectorRegistry:
    """Module-level `connector_type_key -> ConnectorAdapter` map.

    Provider packages (whatsapp/, razorpay/) call `register_adapter` at
    import time. Nothing here is a singleton by accident of Python module
    caching alone being relied on implicitly - `router.py` imports both
    provider adapter modules explicitly for this side effect, the same
    pattern `db/models.py` uses for ORM class registration.
    """

    def __init__(self) -> None:
        self._adapters: dict[str, ConnectorAdapter] = {}

    def register(self, adapter: ConnectorAdapter) -> None:
        self._adapters[adapter.connector_type_key] = adapter

    def get(self, type_key: str) -> ConnectorAdapter:
        try:
            return self._adapters[type_key]
        except KeyError as exc:
            raise LookupError(f"no connector adapter registered for type_key={type_key!r}") from exc

    def get_or_none(self, type_key: str) -> ConnectorAdapter | None:
        return self._adapters.get(type_key)

    def registered_keys(self) -> list[str]:
        return list(self._adapters.keys())

    def all_adapters(self) -> list[ConnectorAdapter]:
        return list(self._adapters.values())


#: Process-wide singleton. Safe: adapters are stateless (each call carries
#: its own session/instance), so one registry per process is sufficient.
registry = ConnectorRegistry()
