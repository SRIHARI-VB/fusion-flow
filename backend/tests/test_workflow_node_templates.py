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

from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.engine.template_resolution import resolve_node_templates

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
