"""Offline tests for the single-source-of-truth module access resolution
(`resolve_module_access[_map]`), role-restriction validation, viewer
read-only enforcement and the module dependency map. Monkeypatch/fake-session
style - no Postgres needed."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fusionflow.core import deps as core_deps
from fusionflow.modules.connectors import router as connector_router
from fusionflow.modules.connectors import service as svc
from fusionflow.modules.connectors.models import ConnectorCategory, ConnectorType
from fusionflow.modules.connectors.module_dependencies import MODULE_DEPENDENCIES, dependents_of
from fusionflow.modules.connectors.schemas import SetRoleRestrictionRequest
from fusionflow.modules.tenancy.models import Business, BusinessStatus, MembershipRole

TENANT = uuid.uuid4()


def _type(key="tickets", category=ConnectorCategory.FEATURE) -> ConnectorType:
    return ConnectorType(
        id=uuid.uuid4(), key=key, category=category, display_name=key,
        config_schema={}, oauth=False, is_enabled_globally=True,
    )


class _Session:
    def __init__(self, business=None, connector_type=None):
        self.business = business
        self.connector_type = connector_type

    async def get(self, model, _id):
        return self.business if model is Business else self.connector_type


def _biz(template=None, status=BusinessStatus.ACTIVE) -> Business:
    return Business(id=TENANT, name="x", slug="x", status=status, business_template_id=template)


def _patch(monkeypatch, raw: str, restricted_ids=()):
    async def _raw(_s, *, tenant_id, connector_type_ids):
        return {i: raw for i in connector_type_ids}

    async def _restr(_s, *, tenant_id, role):
        return set(restricted_ids)

    monkeypatch.setattr(svc, "get_connector_access_map", _raw)
    monkeypatch.setattr(svc, "get_role_restricted_connector_type_ids", _restr)


async def test_grandfathered_and_restricted_for_member(monkeypatch) -> None:
    t = _type()
    _patch(monkeypatch, "not_requested", restricted_ids={t.id})
    s = _Session(_biz())
    assert await svc.resolve_module_access(s, tenant_id=TENANT, connector_type=t, role=MembershipRole.MEMBER) == "restricted"
    assert await svc.resolve_module_access(s, tenant_id=TENANT, connector_type=t, role=MembershipRole.ADMIN) == "granted"
    assert await svc.resolve_module_access(s, tenant_id=TENANT, connector_type=t, role=None) == "granted"


async def test_grandfathered_module_visible_in_map_and_pending_becomes_granted(monkeypatch) -> None:
    a, b = _type("tickets"), _type("orders")
    _patch(monkeypatch, "pending")
    out = await svc.resolve_module_access_map(_Session(_biz()), tenant_id=TENANT, connector_types=[a, b], role=MembershipRole.VIEWER)
    assert out == {a.id: "granted", b.id: "granted"}


async def test_explicit_denial_and_integration_not_rescued(monkeypatch) -> None:
    feature, integ = _type(), _type("whatsapp", ConnectorCategory.MESSAGING)
    _patch(monkeypatch, "denied")
    out = await svc.resolve_module_access_map(_Session(_biz()), tenant_id=TENANT, connector_types=[feature, integ])
    assert set(out.values()) == {"denied"}
    _patch(monkeypatch, "not_requested")
    out = await svc.resolve_module_access_map(_Session(_biz()), tenant_id=TENANT, connector_types=[feature, integ])
    assert out == {feature.id: "granted", integ.id: "not_requested"}


async def test_templated_or_inactive_tenant_not_grandfathered(monkeypatch) -> None:
    t = _type()
    _patch(monkeypatch, "not_requested")
    assert await svc.resolve_module_access(_Session(_biz(template=uuid.uuid4())), tenant_id=TENANT, connector_type=t) == "not_requested"
    assert await svc.resolve_module_access(_Session(_biz(status=BusinessStatus.SUSPENDED)), tenant_id=TENANT, connector_type=t) == "not_requested"


def _ctx():
    return SimpleNamespace(tenant_id=TENANT, role=MembershipRole.OWNER)


async def test_role_restriction_validation(monkeypatch) -> None:
    t = _type()

    def req(role=MembershipRole.MEMBER):
        return SetRoleRestrictionRequest(connector_type_id=t.id, role=role, restricted=True)

    with pytest.raises(HTTPException) as e:  # unknown id
        await connector_router.set_role_restriction(req(), _Session(connector_type=None), _ctx())
    assert e.value.status_code == 404

    integ = _type("whatsapp", ConnectorCategory.MESSAGING)
    with pytest.raises(HTTPException) as e:
        await connector_router.set_role_restriction(req(), _Session(connector_type=integ), _ctx())
    assert e.value.status_code == 400

    limit_only = _type("custom_fields_product")
    with pytest.raises(HTTPException) as e:
        await connector_router.set_role_restriction(req(), _Session(connector_type=limit_only), _ctx())
    assert e.value.status_code == 400

    _patch(monkeypatch, "not_requested")
    with pytest.raises(HTTPException) as e:  # not granted (templated tenant)
        await connector_router.set_role_restriction(req(), _Session(_biz(uuid.uuid4()), t), _ctx())
    assert e.value.status_code == 409

    with pytest.raises(HTTPException) as e:
        await connector_router.set_role_restriction(req(MembershipRole.ADMIN), _Session(_biz(), t), _ctx())
    assert e.value.status_code == 400


def _request(method, path="/api/v1/orders"):
    return SimpleNamespace(method=method, url=SimpleNamespace(path=path))


def test_viewer_write_blocked_but_reads_and_auth_allowed() -> None:
    with pytest.raises(HTTPException) as e:
        core_deps._reject_viewer_write(_request("POST"))
    assert e.value.status_code == 403 and e.value.detail == "Viewers have read-only access."
    core_deps._reject_viewer_write(_request("GET"))
    core_deps._reject_viewer_write(_request("POST", "/api/v1/auth/logout"))
    core_deps._reject_viewer_write(_request("POST", "/api/v1/businesses/abc/switch"))


async def test_enforce_viewer_read_only_uses_claim(monkeypatch) -> None:
    creds = SimpleNamespace(credentials="tok")
    monkeypatch.setattr(core_deps, "decode_access_token", lambda _t: {"tenant_id": "t", "role": "viewer"})
    with pytest.raises(HTTPException):
        await core_deps.enforce_viewer_read_only(_request("DELETE"), creds)
    monkeypatch.setattr(core_deps, "decode_access_token", lambda _t: {"tenant_id": "t", "role": "member"})
    await core_deps.enforce_viewer_read_only(_request("DELETE"), creds)
    await core_deps.enforce_viewer_read_only(_request("DELETE"), None)


def test_dependency_map_sanity() -> None:
    for key, deps in MODULE_DEPENDENCIES.items():
        assert key not in deps
        for d in deps:
            assert d in MODULE_DEPENDENCIES
    assert "orders" in dependents_of("customers")
    assert dependents_of("workflows") == []
