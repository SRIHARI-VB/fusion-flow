"""Regression test for a real bug found interactively: connecting/
disconnecting the WhatsApp connector 500'd, while `GET /connectors` still
showed the instance as `connected`.

Root cause: `connector_service.connect()`/`disconnect()`/`test_connection()`/
`complete_oauth_callback()` all ended with
`await session.refresh(instance, attribute_names=["connector_type"])`. That
relationship was already correctly loaded (via `selectinload` or a direct
constructor assignment) and, with `expire_on_commit=False`, needed no
refresh at all - explicitly refreshing it instead marked it unloaded. The
router then calls `to_instance_out(instance)` synchronously right after,
with no `await` in between, which triggered a lazy DB load for
`instance.connector_type` outside any async/greenlet context -
`sqlalchemy.exc.MissingGreenlet` - an uncaught 500 (the intended `updated_at`
refresh, needed since it's DB-computed via `onupdate=func.now()`, was never
actually the attribute named).

This class of bug is invisible to this suite's usual `FakeSession`-based
offline tests (a hand-rolled fake has no lazy-loading semantics to violate)
- it only reproduces against a real `AsyncSession`/asyncpg backend, hence
`needs_postgres`/`requires_postgres` like `test_rls_isolation.py`.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import delete, select

from fusionflow.db.session import set_tenant_context
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.models import (
    ConnectorCredential,
    ConnectorEvent,
    ConnectorInstance,
    ConnectorOAuthState,
    ConnectorType,
)
from fusionflow.modules.tenancy.models import Business
from tests.conftest import requires_postgres

pytestmark = [pytest.mark.asyncio, pytest.mark.needs_postgres, requires_postgres]


@pytest.fixture(autouse=True)
def _stub_access_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    """This test is about the connect/disconnect *lifecycle*, not the
    access-grant policy (already covered offline in
    `test_connectors_access_gating.py`) - grant unconditionally, same
    monkeypatch trick that file already uses."""

    async def _always_granted(*_args: object, **_kwargs: object) -> bool:
        return True

    monkeypatch.setattr(connector_service, "_tenant_has_connector_access", _always_granted)


async def test_connect_then_disconnect_a_real_whatsapp_instance_does_not_500(pg_session: AsyncSession) -> None:
    # The adapter registry (`base.registry`) is keyed by the fixed,
    # hardcoded "whatsapp" string every adapter module registers at import
    # time - an arbitrary/invented `ConnectorType.key` would find no
    # adapter. Reuse the real seeded row rather than create one.
    connector_type = (
        await pg_session.execute(select(ConnectorType).where(ConnectorType.key == "whatsapp"))
    ).scalar_one_or_none()
    if connector_type is None:
        pytest.skip("no 'whatsapp' ConnectorType seeded in this test database")

    business = Business(id=uuid.uuid4(), name="Live DB Test Co", slug=f"live-db-test-{uuid.uuid4().hex[:8]}")
    pg_session.add(business)
    await pg_session.flush()
    await pg_session.commit()
    await set_tenant_context(pg_session, business.id)

    try:
        instance, _result = await connector_service.connect(
            pg_session,
            tenant_id=business.id,
            type_key=connector_type.key,
            display_name=None,
            params={},
        )
        # The exact call sequence that previously raised MissingGreenlet:
        # a real AsyncSession's relationship access with no `await` in
        # between the DB round-trip above and this synchronous read.
        connected_out = connector_service.to_instance_out(instance)
        assert connected_out.connector_type_key == connector_type.key
        assert connected_out.state.value == "connected"

        disconnected = await connector_service.disconnect(
            pg_session, tenant_id=business.id, instance_id=instance.id
        )
        disconnected_out = connector_service.to_instance_out(disconnected)
        assert disconnected_out.state.value == "disconnected"
    finally:
        # Same session/tenant context as the test itself (RLS-scoped) -
        # child rows first, in FK-dependency order, then the two rows
        # this test created itself.
        await pg_session.execute(
            delete(ConnectorEvent).where(ConnectorEvent.tenant_id == business.id)
        )
        await pg_session.execute(
            delete(ConnectorOAuthState).where(ConnectorOAuthState.tenant_id == business.id)
        )
        await pg_session.execute(
            delete(ConnectorCredential).where(
                ConnectorCredential.connector_instance_id.in_(
                    select(ConnectorInstance.id).where(ConnectorInstance.tenant_id == business.id)
                )
            )
        )
        await pg_session.execute(delete(ConnectorInstance).where(ConnectorInstance.tenant_id == business.id))
        await pg_session.commit()
        # `connector_type` is shared seed data (used by other tests/dev
        # usage too) - only the Business row this test created gets removed.
        await pg_session.execute(delete(Business).where(Business.id == business.id))
        await pg_session.commit()
