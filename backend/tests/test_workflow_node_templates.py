"""Offline unit tests for Part D's `WorkflowNodeTemplate` graph
compilation (`engine.template_resolution.resolve_node_templates`) and the
palette's JSON-schema merge helper (`workflows.service._merge_config_schema`).

The admin CRUD functions themselves (`admin_service.*_workflow_node_template`)
are plain SQLAlchemy-backed catalog CRUD with no special logic beyond what
`create_business_template`/`update_business_template` already establish as
this codebase's tested pattern (and were exercised live against the real
database during development - see this feature's implementation notes);
this file focuses on the genuinely new logic: how a template compiles into
a real, executable node.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from fusionflow.modules.connectors.models import ConnectorCategory, ConnectorState
from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.engine.template_resolution import resolve_node_templates

# Import-for-side-effect: registers every built-in node type (including
# `payments.send_razorpay_link`, used below) with the process-wide
# `node_executor_registry` - see `nodes/__init__.py`'s own docstring for why
# this matches `fusionflow.db.models`'s "import for side effect" pattern.
from fusionflow.modules.workflows import nodes as _nodes  # noqa: F401

pytestmark = pytest.mark.asyncio


def _fake_template(**overrides: Any) -> SimpleNamespace:
    defaults: dict[str, Any] = {
        "id": uuid.uuid4(),
        "key": "send_whatsapp_template",
        "label": "Send WhatsApp Message",
        "description": None,
        "category": "Messaging",
        "base_node_type": "connector.action",
        "icon": None,
        "default_config": {"action": "send_text_message", "connector_instance_id": "abc-123"},
        "config_schema_overrides": None,
        "is_active": True,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class _FakeSession:
    """Not touched by `resolve_node_templates` directly - it only ever
    reaches the DB through `admin_service.list_workflow_node_templates`,
    which every test here monkeypatches."""


async def test_resolve_node_templates_rewrites_matching_node(monkeypatch: pytest.MonkeyPatch) -> None:
    from fusionflow.modules.admin import service as admin_service

    template = _fake_template()

    async def fake_list(session: Any, *, active_only: bool = False) -> list[Any]:
        return [template]

    monkeypatch.setattr(admin_service, "list_workflow_node_templates", fake_list)

    graph = {
        "nodes": [
            {"id": "trigger", "data": {"nodeType": "manual.test_trigger", "config": {}}},
            {
                "id": "send",
                "data": {
                    "nodeType": "send_whatsapp_template",
                    "config": {"params": {"to": "{{trigger.from}}", "body": "hi"}},
                },
            },
        ],
        "edges": [{"id": "e1", "source": "trigger", "target": "send"}],
    }

    compiled = await resolve_node_templates(_FakeSession(), graph)

    send_node = next(n for n in compiled["nodes"] if n["id"] == "send")
    assert send_node["data"]["nodeType"] == "connector.action"
    # Template defaults present, node's own config values layered on top,
    # neither clobbering the other (they're disjoint keys here).
    assert send_node["data"]["config"]["action"] == "send_text_message"
    assert send_node["data"]["config"]["connector_instance_id"] == "abc-123"
    assert send_node["data"]["config"]["params"] == {"to": "{{trigger.from}}", "body": "hi"}
    # The trigger node, not a template key, is untouched.
    trigger_node = next(n for n in compiled["nodes"] if n["id"] == "trigger")
    assert trigger_node["data"]["nodeType"] == "manual.test_trigger"


async def test_resolve_node_templates_node_config_overrides_template_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fusionflow.modules.admin import service as admin_service

    template = _fake_template(default_config={"action": "send_text_message", "params": {"body": "default body"}})

    async def fake_list(session: Any, *, active_only: bool = False) -> list[Any]:
        return [template]

    monkeypatch.setattr(admin_service, "list_workflow_node_templates", fake_list)

    graph = {
        "nodes": [
            {
                "id": "send",
                "data": {"nodeType": "send_whatsapp_template", "config": {"params": {"body": "overridden"}}},
            }
        ],
        "edges": [],
    }

    compiled = await resolve_node_templates(_FakeSession(), graph)

    send_node = next(n for n in compiled["nodes"] if n["id"] == "send")
    # Whole "params" key replaced (shallow merge, not a deep one) - the
    # node's own value for a key it explicitly set always wins.
    assert send_node["data"]["config"]["params"] == {"body": "overridden"}


async def test_resolve_node_templates_is_a_no_op_with_no_active_templates(monkeypatch: pytest.MonkeyPatch) -> None:
    from fusionflow.modules.admin import service as admin_service

    async def fake_list(session: Any, *, active_only: bool = False) -> list[Any]:
        return []

    monkeypatch.setattr(admin_service, "list_workflow_node_templates", fake_list)

    graph = {
        "nodes": [{"id": "n", "data": {"nodeType": "log.noop", "config": {"message": "hi"}}}],
        "edges": [],
    }
    compiled = await resolve_node_templates(_FakeSession(), graph)

    assert compiled == graph


async def test_resolve_node_templates_leaves_non_template_node_types_untouched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fusionflow.modules.admin import service as admin_service

    template = _fake_template(key="only_this_key_matches")

    async def fake_list(session: Any, *, active_only: bool = False) -> list[Any]:
        return [template]

    monkeypatch.setattr(admin_service, "list_workflow_node_templates", fake_list)

    graph = {
        "nodes": [{"id": "n", "data": {"nodeType": "log.noop", "config": {"message": "hi"}}}],
        "edges": [],
    }
    compiled = await resolve_node_templates(_FakeSession(), graph)

    assert compiled["nodes"][0]["data"]["nodeType"] == "log.noop"
    assert compiled["nodes"][0]["data"]["config"] == {"message": "hi"}


async def test_resolve_node_templates_handles_empty_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    from fusionflow.modules.admin import service as admin_service

    async def fake_list(session: Any, *, active_only: bool = False) -> list[Any]:
        return [_fake_template()]

    monkeypatch.setattr(admin_service, "list_workflow_node_templates", fake_list)

    assert await resolve_node_templates(_FakeSession(), None) == {}
    assert await resolve_node_templates(_FakeSession(), {}) == {}


# --------------------------------------------------------------------------
# service._merge_config_schema
# --------------------------------------------------------------------------


async def test_merge_config_schema_returns_base_unchanged_with_no_overrides() -> None:
    base = {"type": "object", "properties": {"action": {"type": "string"}}, "required": ["action"]}
    assert workflows_service._merge_config_schema(base, None) == base


async def test_merge_config_schema_overrides_one_property_without_dropping_others() -> None:
    base = {
        "type": "object",
        "properties": {
            "action": {"type": "string", "title": "Action"},
            "params": {"type": "object", "title": "Params"},
        },
        "required": ["action"],
    }
    overrides = {"properties": {"action": {"type": "string", "title": "Message Type", "default": "send_text_message"}}}

    merged = workflows_service._merge_config_schema(base, overrides)

    assert merged["properties"]["action"] == {
        "type": "string",
        "title": "Message Type",
        "default": "send_text_message",
    }
    assert merged["properties"]["params"] == {"type": "object", "title": "Params"}
    assert merged["required"] == ["action"]


async def test_merge_config_schema_top_level_override_replaces_key() -> None:
    base = {"type": "object", "properties": {}, "required": ["x"]}
    overrides = {"required": []}

    merged = workflows_service._merge_config_schema(base, overrides)

    assert merged["required"] == []


# --------------------------------------------------------------------------
# service.list_node_types_with_templates - field_suggestions for a
# `..._connector_instance_id`-suffixed config field (Fix 1: the connector-
# picker auto-select UX gap for a node like `payments.send_razorpay_link`
# that has more than one connector-instance field, so a single node-level
# `required_connector_type_key` can't disambiguate between them).
# --------------------------------------------------------------------------


class _FakeConnectorType:
    def __init__(self, key: str, display_name: str, category: ConnectorCategory) -> None:
        self.id = uuid.uuid4()
        self.key = key
        self.display_name = display_name
        self.category = category


class _FakeConnectorInstance:
    def __init__(self, connector_type: _FakeConnectorType, display_name: str) -> None:
        self.id = uuid.uuid4()
        self.display_name = display_name
        self.state = ConnectorState.CONNECTED
        self.connector_type_id = connector_type.id
        self.connector_type = connector_type


async def test_list_node_types_with_templates_suggests_options_for_suffixed_connector_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fusionflow.modules.admin import service as admin_service
    from fusionflow.modules.connectors import service as connector_service

    tenant_id = uuid.uuid4()
    whatsapp_type = _FakeConnectorType("whatsapp", "WhatsApp", ConnectorCategory.MESSAGING)
    razorpay_type = _FakeConnectorType("razorpay", "Razorpay", ConnectorCategory.PAYMENT)
    types_by_key = {"whatsapp": whatsapp_type, "razorpay": razorpay_type}

    whatsapp_instance = _FakeConnectorInstance(whatsapp_type, "Main WhatsApp")
    razorpay_instance = _FakeConnectorInstance(razorpay_type, "Main Razorpay")

    async def fake_list_workflow_node_templates(session: Any, *, active_only: bool = False) -> list[Any]:
        return []

    async def fake_list_connector_types(session: Any) -> list[Any]:
        return list(types_by_key.values())

    async def fake_get_connector_type_by_key(session: Any, type_key: str) -> Any:
        return types_by_key.get(type_key)

    async def fake_list_instances(session: Any, tenant_id: uuid.UUID) -> list[Any]:
        return [whatsapp_instance, razorpay_instance]

    async def fake_get_connector_access_map(
        session: Any, *, tenant_id: uuid.UUID, connector_type_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        # Every connector type this test knows about is granted - the point
        # of this test is the field-suggestion suffix matching, not
        # entitlement gating itself (already covered elsewhere).
        return {type_id: "granted" for type_id in connector_type_ids}

    monkeypatch.setattr(admin_service, "list_workflow_node_templates", fake_list_workflow_node_templates)
    monkeypatch.setattr(connector_service, "list_connector_types", fake_list_connector_types)
    monkeypatch.setattr(connector_service, "get_connector_type_by_key", fake_get_connector_type_by_key)
    monkeypatch.setattr(connector_service, "list_instances", fake_list_instances)
    monkeypatch.setattr(connector_service, "get_connector_access_map", fake_get_connector_access_map)

    entries = await workflows_service.list_node_types_with_templates(SimpleNamespace(), tenant_id=tenant_id)

    razorpay_node = next(e for e in entries if e.node_type == "payments.send_razorpay_link")
    assert razorpay_node.field_suggestions is not None
    assert razorpay_node.field_suggestions["razorpay_connector_instance_id"] == [
        {"value": str(razorpay_instance.id), "label": razorpay_instance.display_name}
    ]
    assert razorpay_node.field_suggestions["whatsapp_connector_instance_id"] == [
        {"value": str(whatsapp_instance.id), "label": whatsapp_instance.display_name}
    ]


# --------------------------------------------------------------------------
# admin.router.list_admin_node_types - GET /api/admin/node-types
# --------------------------------------------------------------------------
#
# No HTTP-level (TestClient) admin route tests exist anywhere in this
# codebase today (admin routes are otherwise only exercised live against a
# real database, per this file's own module docstring) - this calls the
# route function directly, the same way FastAPI route functions are
# ordinary async functions, to stay consistent with that convention rather
# than introducing a new HTTP-testing pattern for one route.


async def test_list_admin_node_types_reflects_the_real_engine_registry() -> None:
    from fusionflow.modules.admin.router import list_admin_node_types
    from fusionflow.modules.admin.schemas import AdminNodeTypeSummaryOut

    # `_admin: PlatformAdminDep` is a type-only auth gate FastAPI enforces
    # via dependency injection at the HTTP layer - calling the plain
    # function directly, unrelated to what it validates, needs no real
    # value here.
    results = await list_admin_node_types(_admin=None)

    assert all(isinstance(r, AdminNodeTypeSummaryOut) for r in results)
    node_types = {r.node_type for r in results}
    # These are exactly the base_node_type values the seed scripts already
    # use that the old hardcoded frontend dropdown was missing - the whole
    # reason this endpoint exists.
    assert "connector.action" in node_types
    assert "module.list" in node_types
    assert "module.create" in node_types
