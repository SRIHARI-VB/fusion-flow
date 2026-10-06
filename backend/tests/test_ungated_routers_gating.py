"""Routers that previously had no module entitlement gate: assert the gate
is bound (router-level dependency) with the right key, and that a denied
tenant is refused with 403 (inbox-style router dependency and the
in-handler appointment check in business_objects)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from fusionflow.core.deps import TenantContext
from fusionflow.modules.broadcast_campaigns.router import router as broadcast_router
from fusionflow.modules.business_objects import router as bo_router
from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.connectors.instagram.router import router as instagram_router
from fusionflow.modules.connectors.models import ConnectorCategory, ConnectorType
from fusionflow.modules.connectors.whatsapp.router import router as whatsapp_router
from fusionflow.modules.inbox.router import router as inbox_router
from fusionflow.modules.media_library.router import router as media_router
from fusionflow.modules.predefined_automations.router import router as automations_router
from fusionflow.modules.quick_replies.router import router as quick_replies_router
from fusionflow.modules.tenancy.models import MembershipRole

_TYPE_ID = uuid.uuid4()
_CONTEXT = TenantContext(tenant_id=uuid.uuid4(), role=MembershipRole.OWNER, user=object())


def _gate_dependency(router):
    deps = [d.dependency for d in router.dependencies]
    gates = [d for d in deps if d.__qualname__.startswith("require_module_access")]
    assert len(gates) == 1
    return gates[0]


def _patch_status(monkeypatch, key: str, resolved: str) -> None:
    ctype = ConnectorType(
        id=_TYPE_ID, key=key, category=ConnectorCategory.FEATURE, display_name=key,
        config_schema={}, oauth=False, is_enabled_globally=True,
    )

    async def _lookup(_session, _key):
        return ctype

    async def _map(_session, **kwargs):
        return {_TYPE_ID: resolved}

    monkeypatch.setattr(connector_service, "get_connector_type_by_key", _lookup)
    monkeypatch.setattr(connector_service, "get_connector_access_map", _map, raising=False)
    monkeypatch.setattr(connector_service, "get_connector_access_map_for_role", _map, raising=False)


@pytest.mark.parametrize(
    "router",
    [inbox_router, broadcast_router, media_router, quick_replies_router, automations_router,
     whatsapp_router, instagram_router],
)
async def test_router_has_gate_and_denied_is_403(router, monkeypatch) -> None:
    gate = _gate_dependency(router)
    _patch_status(monkeypatch, "x", "denied")
    with pytest.raises(HTTPException) as exc:
        await gate(_CONTEXT, object())
    assert exc.value.status_code == 403


def test_gate_keys() -> None:
    for router, key in [
        (inbox_router, "communication"), (broadcast_router, "communication"),
        (media_router, "communication"), (quick_replies_router, "communication"),
        (automations_router, "communication"), (whatsapp_router, "whatsapp"),
        (instagram_router, "instagram"),
    ]:
        closure = {c.cell_contents for c in (_gate_dependency(router).__closure__ or ())}
        assert key in closure


async def test_business_objects_gates_only_appointment_type(monkeypatch) -> None:
    _patch_status(monkeypatch, "appointments", "denied")
    await bo_router._ensure_appointments_access(_CONTEXT, object(), "delivery")  # open
    with pytest.raises(HTTPException) as exc:
        await bo_router._ensure_appointments_access(_CONTEXT, object(), "appointment")
    assert exc.value.status_code == 403


async def test_business_objects_record_by_id_gated_for_appointment(monkeypatch) -> None:
    _patch_status(monkeypatch, "appointments", "denied")

    async def _get_type(_session, *, tenant_id, object_type_id):
        return SimpleNamespace(key="appointment")

    monkeypatch.setattr(bo_router.business_objects_service, "get_object_type", _get_type)
    with pytest.raises(HTTPException) as exc:
        await bo_router._ensure_record_access(_CONTEXT, object(), SimpleNamespace(object_type_id=_TYPE_ID))
    assert exc.value.status_code == 403
