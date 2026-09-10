"""Offline unit tests for the connector-access-request gating logic added to
`modules/connectors/service.py` (business-template bundle, or an approved
`ConnectorAccessRequest`, gates `connect()`).

No Postgres needed - same fake-`AsyncSession`-with-queued-results approach
as `test_admin_plan_entitlements.py`. `Business.business_template_id`
doesn't exist on the ORM model in this checkout yet (see this task's
report); `SimpleNamespace(business_template_id=...)` stands in for "a
Business row once that column exists" - the exact duck-typed access
pattern `service.py` uses via `getattr(..., None)`.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.models import (
    ConnectorAccessRequest,
    ConnectorAccessRequestStatus,
    ConnectorCategory,
    ConnectorType,
)
from fusionflow.modules.connectors.service import ConnectorError

_TENANT_ID = uuid.uuid4()
_TEMPLATE_ID = uuid.uuid4()
_CONNECTOR_TYPE_ID = uuid.uuid4()
_OTHER_CONNECTOR_TYPE_ID = uuid.uuid4()


def _connector_type() -> ConnectorType:
    return ConnectorType(
        id=_CONNECTOR_TYPE_ID,
        key="razorpay",
        category=ConnectorCategory.PAYMENT,
        display_name="Razorpay",
        config_schema={},
        oauth=False,
        is_enabled_globally=True,
    )


def _access_request(status: ConnectorAccessRequestStatus, *, created_at=None) -> ConnectorAccessRequest:
    import datetime as _dt

    return ConnectorAccessRequest(
        id=uuid.uuid4(),
        tenant_id=_TENANT_ID,
        connector_type_id=_CONNECTOR_TYPE_ID,
        status=status,
        requested_by=uuid.uuid4(),
        reason=None,
        created_at=created_at or _dt.datetime(2024, 1, 1, tzinfo=_dt.timezone.utc),
    )


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._value


class _FakeSession:
    """Same queued-results fake as the admin-service tests - see that
    module's docstring for the rationale."""

    def __init__(self, execute_results: list, get_result=None):
        self._execute_results = list(execute_results)
        self._get_result = get_result

    async def execute(self, *_args, **_kwargs):
        return _Result(self._execute_results.pop(0))

    async def get(self, *_args, **_kwargs):
        return self._get_result


# --------------------------------------------------------------------------
# get_connector_access_map / _bundled_connector_type_ids
# --------------------------------------------------------------------------


async def test_bundled_connector_type_is_granted_with_no_access_request_needed() -> None:
    business = SimpleNamespace(business_template_id=_TEMPLATE_ID)
    session = _FakeSession(
        execute_results=[[_CONNECTOR_TYPE_ID], []],  # bundle ids, then access requests
        get_result=business,
    )
    access_map = await connector_service.get_connector_access_map(
        session, tenant_id=_TENANT_ID, connector_type_ids=[_CONNECTOR_TYPE_ID]
    )
    assert access_map[_CONNECTOR_TYPE_ID] == "granted"


async def test_no_bundle_and_no_request_is_not_requested() -> None:
    business = SimpleNamespace(business_template_id=None)
    session = _FakeSession(execute_results=[[]], get_result=business)  # access requests
    access_map = await connector_service.get_connector_access_map(
        session, tenant_id=_TENANT_ID, connector_type_ids=[_CONNECTOR_TYPE_ID]
    )
    assert access_map[_CONNECTOR_TYPE_ID] == "not_requested"


async def test_business_missing_business_template_id_attribute_is_safe() -> None:
    """Forward-compat guard: before the migration lands, a real Business
    instance has no `business_template_id` attribute at all."""
    business = SimpleNamespace()  # no business_template_id attribute
    session = _FakeSession(execute_results=[[]], get_result=business)
    access_map = await connector_service.get_connector_access_map(
        session, tenant_id=_TENANT_ID, connector_type_ids=[_CONNECTOR_TYPE_ID]
    )
    assert access_map[_CONNECTOR_TYPE_ID] == "not_requested"


async def test_pending_request_outside_bundle_is_pending() -> None:
    business = SimpleNamespace(business_template_id=None)
    request = _access_request(ConnectorAccessRequestStatus.PENDING)
    session = _FakeSession(execute_results=[[request]], get_result=business)
    access_map = await connector_service.get_connector_access_map(
        session, tenant_id=_TENANT_ID, connector_type_ids=[_CONNECTOR_TYPE_ID]
    )
    assert access_map[_CONNECTOR_TYPE_ID] == "pending"


async def test_approved_request_outside_bundle_is_granted() -> None:
    business = SimpleNamespace(business_template_id=None)
    request = _access_request(ConnectorAccessRequestStatus.APPROVED)
    session = _FakeSession(execute_results=[[request]], get_result=business)
    access_map = await connector_service.get_connector_access_map(
        session, tenant_id=_TENANT_ID, connector_type_ids=[_CONNECTOR_TYPE_ID]
    )
    assert access_map[_CONNECTOR_TYPE_ID] == "granted"


async def test_denied_request_outside_bundle_is_denied() -> None:
    business = SimpleNamespace(business_template_id=None)
    request = _access_request(ConnectorAccessRequestStatus.DENIED)
    session = _FakeSession(execute_results=[[request]], get_result=business)
    access_map = await connector_service.get_connector_access_map(
        session, tenant_id=_TENANT_ID, connector_type_ids=[_CONNECTOR_TYPE_ID]
    )
    assert access_map[_CONNECTOR_TYPE_ID] == "denied"


# --------------------------------------------------------------------------
# connect() gating wiring
# --------------------------------------------------------------------------


async def test_connect_raises_403_when_access_not_granted(monkeypatch) -> None:
    connector_type = _connector_type()

    async def _fake_get_connector_type_by_key(_session, _type_key):
        return connector_type

    async def _fake_has_access(_session, *, tenant_id, connector_type_id):
        return False

    def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("adapter registry should never be consulted when access is denied")

    monkeypatch.setattr(connector_service, "get_connector_type_by_key", _fake_get_connector_type_by_key)
    monkeypatch.setattr(connector_service, "_tenant_has_connector_access", _fake_has_access)
    monkeypatch.setattr(connector_service.base.registry, "get_or_none", _fail_if_called)

    with pytest.raises(ConnectorError) as exc_info:
        await connector_service.connect(
            object(),  # never reaches a real session - gating raises first
            tenant_id=_TENANT_ID,
            type_key="razorpay",
            display_name=None,
            params={},
        )
    assert exc_info.value.status_code == 403
    assert "request access" in exc_info.value.detail.lower()


async def test_connect_proceeds_past_the_gate_when_access_is_granted(monkeypatch) -> None:
    connector_type = _connector_type()

    async def _fake_get_connector_type_by_key(_session, _type_key):
        return connector_type

    async def _fake_has_access(_session, *, tenant_id, connector_type_id):
        return True

    class _Reached(Exception):
        pass

    def _reached_adapter_lookup(_type_key):
        # The point of this test is only that we got *past* the access
        # gate to reach this call - what happens after is out of scope.
        raise _Reached()

    monkeypatch.setattr(connector_service, "get_connector_type_by_key", _fake_get_connector_type_by_key)
    monkeypatch.setattr(connector_service, "_tenant_has_connector_access", _fake_has_access)
    monkeypatch.setattr(connector_service.base.registry, "get_or_none", _reached_adapter_lookup)

    with pytest.raises(_Reached):
        await connector_service.connect(
            object(),
            tenant_id=_TENANT_ID,
            type_key="razorpay",
            display_name=None,
            params={},
        )
