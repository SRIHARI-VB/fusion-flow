"""Offline unit tests for `modules/connectors/deps.py::require_module_access`
— the gate applied to the 11 fixed-module routers (products, orders,
tickets, ...).

Same fake-session/monkeypatch approach as `test_connectors_access_gating.py`
and `test_admin_plan_entitlements.py` - no Postgres needed, this module's
own logic branches only on already-unit-tested `connector_service` calls
plus one direct `session.get(Business, ...)` for the grandfathering check.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from fusionflow.core.deps import TenantContext
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.deps import require_module_access
from fusionflow.modules.connectors.models import ConnectorCategory, ConnectorType
from fusionflow.modules.tenancy.models import Business, BusinessStatus, MembershipRole

_TENANT_ID = uuid.uuid4()
_MODULE_TYPE_ID = uuid.uuid4()


def _feature_connector_type() -> ConnectorType:
    return ConnectorType(
        id=_MODULE_TYPE_ID,
        key="tickets",
        category=ConnectorCategory.FEATURE,
        display_name="Tickets",
        config_schema={},
        oauth=False,
        is_enabled_globally=True,
    )


def _context() -> TenantContext:
    return TenantContext(tenant_id=_TENANT_ID, role=MembershipRole.OWNER, user=object())


def _business(*, business_template_id, status) -> Business:
    return Business(
        id=_TENANT_ID,
        name="Test Co",
        slug="test-co",
        status=status,
        business_template_id=business_template_id,
    )


class _FakeSession:
    def __init__(self, *, get_result):
        self._get_result = get_result

    async def get(self, *_args, **_kwargs):
        return self._get_result


async def test_unregistered_module_key_raises_500(monkeypatch) -> None:
    async def _fake_lookup(_session, _key):
        return None

    monkeypatch.setattr(connector_service, "get_connector_type_by_key", _fake_lookup)

    dependency = require_module_access("not_a_real_module")
    with pytest.raises(HTTPException) as exc_info:
        await dependency(_context(), _FakeSession(get_result=None))
    assert exc_info.value.status_code == 500


async def test_grandfathered_tenant_with_no_template_is_granted(monkeypatch) -> None:
    """COMPAT branch: a pre-template-system ACTIVE tenant gets free access
    to FEATURE-category modules."""
    connector_type = _feature_connector_type()

    async def _fake_lookup(_session, _key):
        return connector_type

    async def _fail_if_called(*_args, **_kwargs):
        raise AssertionError("the normal entitlement check should be skipped for grandfathered tenants")

    monkeypatch.setattr(connector_service, "get_connector_type_by_key", _fake_lookup)
    monkeypatch.setattr(connector_service, "_tenant_has_connector_access", _fail_if_called)

    business = _business(business_template_id=None, status=BusinessStatus.ACTIVE)
    session = _FakeSession(get_result=business)

    dependency = require_module_access("tickets")
    result = await dependency(_context(), session)
    assert result.tenant_id == _TENANT_ID


async def test_templated_tenant_without_module_in_bundle_is_denied(monkeypatch) -> None:
    connector_type = _feature_connector_type()

    async def _fake_lookup(_session, _key):
        return connector_type

    async def _fake_has_access(_session, *, tenant_id, connector_type_id):
        return False

    monkeypatch.setattr(connector_service, "get_connector_type_by_key", _fake_lookup)
    monkeypatch.setattr(connector_service, "_tenant_has_connector_access", _fake_has_access)

    business = _business(business_template_id=uuid.uuid4(), status=BusinessStatus.ACTIVE)
    session = _FakeSession(get_result=business)

    dependency = require_module_access("tickets")
    with pytest.raises(HTTPException) as exc_info:
        await dependency(_context(), session)
    assert exc_info.value.status_code == 403


async def test_templated_tenant_with_module_in_bundle_is_granted(monkeypatch) -> None:
    connector_type = _feature_connector_type()

    async def _fake_lookup(_session, _key):
        return connector_type

    async def _fake_has_access(_session, *, tenant_id, connector_type_id):
        return True

    monkeypatch.setattr(connector_service, "get_connector_type_by_key", _fake_lookup)
    monkeypatch.setattr(connector_service, "_tenant_has_connector_access", _fake_has_access)

    business = _business(business_template_id=uuid.uuid4(), status=BusinessStatus.ACTIVE)
    session = _FakeSession(get_result=business)

    dependency = require_module_access("tickets")
    result = await dependency(_context(), session)
    assert result.tenant_id == _TENANT_ID


async def test_approved_access_request_grants_a_feature_module(monkeypatch) -> None:
    """Mirrors how an approved ConnectorAccessRequest already grants an
    integration-kind connector - the same mechanism works unmodified for
    a feature-kind module outside its tenant's template bundle."""
    connector_type = _feature_connector_type()

    async def _fake_lookup(_session, _key):
        return connector_type

    async def _fake_has_access(_session, *, tenant_id, connector_type_id):
        # Stands in for get_connector_access_map resolving an APPROVED
        # ConnectorAccessRequest row - that resolution path is already
        # covered by test_connectors_access_gating.py.
        return True

    monkeypatch.setattr(connector_service, "get_connector_type_by_key", _fake_lookup)
    monkeypatch.setattr(connector_service, "_tenant_has_connector_access", _fake_has_access)

    # status is not ACTIVE, so the grandfathering compat branch (which
    # requires status == ACTIVE) never triggers here even with no
    # business_template_id - this isolates the fallthrough to the
    # (mocked) approved-request resolution, rather than accidentally
    # passing via the grandfather branch instead.
    business = _business(business_template_id=None, status=BusinessStatus.SUSPENDED)
    session = _FakeSession(get_result=business)

    dependency = require_module_access("tickets")
    result = await dependency(_context(), session)
    assert result.tenant_id == _TENANT_ID
