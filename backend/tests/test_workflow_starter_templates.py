"""Tests for `WorkflowStarterTemplate` (composable-workflow-builder
redesign, Phase 6): the ready-to-use example workflows a tenant can start
a new workflow from, and the instantiate-from-template flow that
auto-provisions any custom business object type a template's graph
assumes exists.

Split the same way `test_workflow_business_objects.py`/`test_workflow_composite_branching.py`
are:

* Offline (default, no Postgres): the two real seeded graphs
  (`scripts/seed_workflow_starter_templates.py`) run through the exact
  compile+validate pipeline `publish_workflow` uses, against a
  `FakeSession` (same shape as `test_workflows_engine.py`'s) - proving
  every rule *except* connector-reference passes cleanly (a global
  template can never know which of a tenant's own connected instances to
  reference - see that script's module docstring).
* `requires_postgres`: the actual instantiate flow needs real `businesses`/
  `workflows` rows (FK-backed) and RLS-scoped tenant isolation - skips
  (not fails) without `$TEST_DATABASE_URL`, same as `test_rls_isolation.py`.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from fusionflow.modules.admin import service as admin_service
from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.template_resolution import resolve_composite_branches
from fusionflow.modules.workflows.validation import validate_for_publish
from scripts.seed_workflow_starter_templates import (
    _APPOINTMENT_CANCELLATION_GRAPH,
    _APPOINTMENT_GRAPH,
    _APPOINTMENT_REQUIRED_OBJECT_TYPES,
    _BROADCAST_MESSAGE_GRAPH,
    _FAQ_AUTORESPONDER_GRAPH,
    _FEEDBACK_GRAPH,
    _LEAD_CAPTURE_GRAPH,
    _MARKETING_OPTIN_GRAPH,
    _MARKETING_TEMPLATE_BROADCAST_GRAPH,
    _ORDER_CONFIRMATION_GRAPH,
    _ORDER_STATUS_GRAPH,
    _ORDERING_GRAPH,
    _PRODUCT_AVAILABILITY_GRAPH,
    _REENGAGEMENT_BLAST_GRAPH,
    _RESTAURANT_CART_ORDERING_GRAPH,
    _RESTAURANT_RESERVATION_GRAPH,
    _RETURN_REQUEST_GRAPH,
    _SUPPORT_TICKET_GRAPH,
    _WELCOME_MENU_GRAPH,
)
from tests.conftest import requires_postgres


class _FakeSession:
    """Stands in for an `AsyncSession` for `validate_for_publish`'s rule 2
    (`_check_connector_references`) - `get` always returns `None`, i.e.
    "no such connector instance", exactly what a fresh, never-configured
    tenant sees for the seeded templates' placeholder connector ids."""

    async def get(self, model: Any, ident: Any) -> Any:
        return None


# ---------------------------------------------------------------------------
# Offline: both seeded graphs validate cleanly except connector references
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "graph_json",
    [
        _ORDERING_GRAPH,
        _APPOINTMENT_GRAPH,
        _SUPPORT_TICKET_GRAPH,
        _ORDER_CONFIRMATION_GRAPH,
        _FEEDBACK_GRAPH,
        _ORDER_STATUS_GRAPH,
        _PRODUCT_AVAILABILITY_GRAPH,
        _LEAD_CAPTURE_GRAPH,
        _MARKETING_OPTIN_GRAPH,
        _RETURN_REQUEST_GRAPH,
        _APPOINTMENT_CANCELLATION_GRAPH,
        _RESTAURANT_RESERVATION_GRAPH,
        _FAQ_AUTORESPONDER_GRAPH,
        _WELCOME_MENU_GRAPH,
        _RESTAURANT_CART_ORDERING_GRAPH,
        _BROADCAST_MESSAGE_GRAPH,
        _MARKETING_TEMPLATE_BROADCAST_GRAPH,
        _REENGAGEMENT_BLAST_GRAPH,
    ],
    ids=[
        "whatsapp_ordering",
        "appointment_booking",
        "whatsapp_support_ticket",
        "order_confirmation_broadcast",
        "post_purchase_feedback",
        "order_status_check",
        "product_availability_check",
        "lead_capture",
        "marketing_optin",
        "return_request",
        "appointment_cancellation",
        "restaurant_reservation",
        "faq_autoresponder",
        "welcome_menu",
        "restaurant_cart_ordering",
        "broadcast_message",
        "marketing_template_broadcast",
        "reengagement_blast",
    ],
)
async def test_seeded_template_graph_validates_cleanly_except_connector_references(graph_json: dict) -> None:
    compiled = resolve_composite_branches(graph_json)
    graph = WorkflowGraph.from_json(compiled)
    result = await validate_for_publish(_FakeSession(), tenant_id=uuid.uuid4(), graph=graph)

    assert result.issues, "expected at least the placeholder connector-reference errors"
    rules = {issue.rule for issue in result.issues}
    assert rules == {"disconnected_connector_reference"}, (
        f"unexpected non-connector validation issues: {[i.to_dict() for i in result.issues if i.rule != 'disconnected_connector_reference']}"
    )
    assert all(issue.severity == "error" for issue in result.issues)


# ---------------------------------------------------------------------------
# requires_postgres: the real instantiate-from-template flow
# ---------------------------------------------------------------------------


@pytest.fixture
async def two_businesses(pg_session_factory):
    from sqlalchemy import text

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    async with pg_session_factory() as session:
        for tenant_id, name in ((tenant_a, "Starter Tenant A"), (tenant_b, "Starter Tenant B")):
            await session.execute(
                text("INSERT INTO businesses (id, name, slug, status) VALUES (:id, :name, :slug, 'active')"),
                {"id": tenant_id, "name": name, "slug": f"starter-{tenant_id.hex[:12]}"},
            )
        await session.commit()

    yield tenant_a, tenant_b

    async with pg_session_factory() as session:
        await session.execute(text("DELETE FROM businesses WHERE id = ANY(:ids)"), {"ids": [tenant_a, tenant_b]})
        await session.commit()


@pytest.fixture
async def appointment_template(pg_session_factory):
    """A real `WorkflowStarterTemplate` row (global, no RLS) using the
    actual seeded appointment-booking graph + its `required_object_types`
    spec - exercising the real auto-provisioning path, not a synthetic one."""
    from fusionflow.modules.admin import service as admin_service

    async with pg_session_factory() as session:
        template = await admin_service.create_workflow_starter_template(
            session,
            key=f"test-appointment-{uuid.uuid4().hex[:8]}",
            name="Test Appointment Booking",
            description="Test copy of the seeded appointment-booking template.",
            category="Appointments",
            icon="calendar",
            graph_json=_APPOINTMENT_GRAPH,
            required_object_types=_APPOINTMENT_REQUIRED_OBJECT_TYPES,
            is_active=True,
        )
        await session.commit()
        template_id = template.id

    yield template_id

    async with pg_session_factory() as session:
        await admin_service.delete_workflow_starter_template(session, template_id)
        await session.commit()


@requires_postgres
async def test_create_workflow_from_starter_template_provisions_object_type_and_seeds_graph(
    pg_session_factory, two_businesses, appointment_template
) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.business_objects import service as business_objects_service

    tenant_a, _ = two_businesses
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        workflow = await workflows_service.create_workflow_from_starter_template(
            session,
            tenant_id=tenant_a,
            name="My appointment flow",
            starter_template_id=appointment_template,
            created_by=uuid.uuid4(),
        )
        await session.commit()

        await set_tenant_context(session, tenant_a)
        object_type = await business_objects_service.get_object_type_by_key(
            session, tenant_id=tenant_a, key="appointment"
        )
        assert object_type is not None
        assert object_type.name == "Appointment"
        field_defs = await business_objects_service.list_field_definitions(
            session, tenant_id=tenant_a, object_type_id=object_type.id
        )
        assert {f.key for f in field_defs} == {"service", "preferred_time", "status"}

        version = await workflows_service.get_latest_version(session, workflow.id)
        assert version is not None
        assert version.graph == _APPOINTMENT_GRAPH


@requires_postgres
async def test_create_workflow_from_starter_template_does_not_duplicate_existing_object_type(
    pg_session_factory, two_businesses, appointment_template
) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.business_objects import service as business_objects_service
    from fusionflow.modules.business_objects.schemas import ObjectTypeUpdate

    tenant_a, _ = two_businesses
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        await workflows_service.create_workflow_from_starter_template(
            session,
            tenant_id=tenant_a,
            name="First appointment flow",
            starter_template_id=appointment_template,
            created_by=uuid.uuid4(),
        )
        await session.commit()

    # A tenant who already customized their "appointment" object type
    # (e.g. renamed it) should never have it silently recreated/overwritten
    # by starting a second workflow from the same template.
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        object_type = await business_objects_service.get_object_type_by_key(
            session, tenant_id=tenant_a, key="appointment"
        )
        assert object_type is not None
        await business_objects_service.update_object_type(
            session, object_type, ObjectTypeUpdate(name="My Custom Appointment Name")
        )
        await session.commit()

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        await workflows_service.create_workflow_from_starter_template(
            session,
            tenant_id=tenant_a,
            name="Second appointment flow",
            starter_template_id=appointment_template,
            created_by=uuid.uuid4(),
        )
        await session.commit()

        await set_tenant_context(session, tenant_a)
        all_types = await business_objects_service.list_object_types(session, tenant_id=tenant_a)
        appointment_types = [t for t in all_types if t.key == "appointment"]
        assert len(appointment_types) == 1
        assert appointment_types[0].name == "My Custom Appointment Name"


@requires_postgres
async def test_create_workflow_from_starter_template_isolates_object_types_per_tenant(
    pg_session_factory, two_businesses, appointment_template
) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.business_objects import service as business_objects_service

    tenant_a, tenant_b = two_businesses

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        await workflows_service.create_workflow_from_starter_template(
            session,
            tenant_id=tenant_a,
            name="Tenant A's appointment flow",
            starter_template_id=appointment_template,
            created_by=uuid.uuid4(),
        )
        await session.commit()

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_b)
        await workflows_service.create_workflow_from_starter_template(
            session,
            tenant_id=tenant_b,
            name="Tenant B's appointment flow",
            starter_template_id=appointment_template,
            created_by=uuid.uuid4(),
        )
        await session.commit()

        await set_tenant_context(session, tenant_b)
        type_a = await business_objects_service.get_object_type_by_key(session, tenant_id=tenant_a, key="appointment")
        type_b = await business_objects_service.get_object_type_by_key(session, tenant_id=tenant_b, key="appointment")
        assert type_a is None  # RLS: tenant B's session can never see tenant A's row
        assert type_b is not None


# ---------------------------------------------------------------------------
# Offline: auto-derived `required_connector_type_keys` + the "Validate" route
# ---------------------------------------------------------------------------


class _FakeValidateSession:
    """Stands in for an `AsyncSession` for the compile+validate pipeline:
    `resolve_node_templates` calls `.execute(select(WorkflowNodeTemplate)...)`
    (empty catalog - no active node templates to rewrite) and
    `_check_connector_references` calls `.get(...)` (always `None` - no
    real connector instance for any placeholder id, exactly what a
    never-configured tenant would see)."""

    class _EmptyScalars:
        def scalars(self):
            return self

        def all(self):
            return []

    async def execute(self, *_args, **_kwargs):
        return self._EmptyScalars()

    async def get(self, *_args, **_kwargs):
        return None


def test_compute_required_connector_type_keys_picks_up_whatsapp_trigger() -> None:
    graph = {
        "nodes": [
            {"id": "n1", "data": {"nodeType": "whatsapp.message_received", "config": {}}},
        ],
        "edges": [],
    }
    assert admin_service.compute_required_connector_type_keys(graph) == ["whatsapp"]


def test_compute_required_connector_type_keys_is_empty_for_a_graph_with_no_gated_nodes() -> None:
    graph = {"nodes": [{"id": "n1", "data": {"nodeType": "condition.field_compare", "config": {}}}], "edges": []}
    assert admin_service.compute_required_connector_type_keys(graph) == []


async def test_validate_starter_template_graph_reports_only_connector_reference_issues() -> None:
    """The real seeded ordering graph, run through `admin_service.validate_starter_template_graph`
    (the same function the `POST /api/admin/workflow-starter-templates/validate`
    route calls) - every placeholder connector reference is expected to
    fail rule 2; that's the accepted passing bar for a template, matching
    `test_seeded_template_graph_validates_cleanly_except_connector_references`
    above."""
    issues, required_keys = await admin_service.validate_starter_template_graph(
        _FakeValidateSession(), _ORDERING_GRAPH
    )
    assert issues, "expected at least the placeholder connector-reference errors"
    assert {i.rule for i in issues} == {"disconnected_connector_reference"}
    assert "whatsapp" in required_keys


async def test_validate_workflow_starter_template_route_returns_shared_result_shape() -> None:
    from fusionflow.modules.admin.router import validate_workflow_starter_template
    from fusionflow.modules.admin.schemas import GraphValidationResultOut, ValidateStarterTemplateRequest

    result = await validate_workflow_starter_template(
        ValidateStarterTemplateRequest(graph_json=_ORDERING_GRAPH),
        _admin=None,
        session=_FakeValidateSession(),
    )
    assert isinstance(result, GraphValidationResultOut)
    assert {i.rule for i in result.issues} == {"disconnected_connector_reference"}
    assert "whatsapp" in result.required_connector_type_keys


# ---------------------------------------------------------------------------
# compute_workflow_purpose: server-computed "automation"/"broadcast" tag,
# derived straight from a template's own stored graph - no new DB column.
# ---------------------------------------------------------------------------


def _single_trigger_graph(node_type: str) -> dict:
    return {
        "nodes": [
            {
                "id": "trigger",
                "type": "trigger",
                "data": {"nodeType": node_type, "config": {}, "label": "Trigger"},
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }


def test_compute_workflow_purpose_automation_trigger_returns_automation() -> None:
    from fusionflow.modules.admin import service as admin_service

    graph = _single_trigger_graph("whatsapp.message_received")
    assert admin_service.compute_workflow_purpose(graph) == "automation"


def test_compute_workflow_purpose_broadcast_trigger_returns_broadcast() -> None:
    from fusionflow.modules.admin import service as admin_service

    graph = _single_trigger_graph("broadcast.scheduled_send")
    assert admin_service.compute_workflow_purpose(graph) == "broadcast"


class _FakeTriggerDefinition:
    def __init__(self, applicable_purposes: list[str] | None) -> None:
        self.applicable_purposes = applicable_purposes


def test_compute_workflow_purpose_both_purposes_shape_returns_none(monkeypatch: "pytest.MonkeyPatch") -> None:
    """Only the two single-purpose-exclusive shapes resolve to something -
    a trigger tagged applicable to both shows for either purpose (`None`),
    same as an untagged one."""
    from fusionflow.modules.workflows.engine.registry import trigger_registry

    monkeypatch.setattr(
        trigger_registry, "get", lambda node_type: _FakeTriggerDefinition(["automation", "broadcast"])
    )
    from fusionflow.modules.admin import service as admin_service

    graph = _single_trigger_graph("some.trigger")
    assert admin_service.compute_workflow_purpose(graph) is None


def test_compute_workflow_purpose_manual_test_trigger_returns_none() -> None:
    """`manual.test_trigger` declares no `applicable_purposes` - shown for
    either purpose, not treated as an error."""
    from fusionflow.modules.admin import service as admin_service

    graph = _single_trigger_graph("manual.test_trigger")
    assert admin_service.compute_workflow_purpose(graph) is None


def test_compute_workflow_purpose_unregistered_trigger_returns_none() -> None:
    """A template referencing a since-deleted/unknown trigger node type
    must not raise - it degrades to "shown for either purpose", same as
    any other unresolvable case."""
    from fusionflow.modules.admin import service as admin_service

    graph = _single_trigger_graph("some.trigger_type_that_was_removed")
    assert admin_service.compute_workflow_purpose(graph) is None


def test_compute_workflow_purpose_no_trigger_node_returns_none() -> None:
    from fusionflow.modules.admin import service as admin_service

    assert admin_service.compute_workflow_purpose({"nodes": [], "edges": []}) is None


def test_compute_workflow_purpose_falls_back_to_trigger_typed_node_when_id_is_not_literally_trigger() -> None:
    """A hand-authored graph that doesn't happen to name its trigger node
    `"trigger"` (every seeded template does, by convention) still resolves
    via the node's own `type: "trigger"`."""
    from fusionflow.modules.admin import service as admin_service

    graph = {
        "nodes": [
            {
                "id": "start_here",
                "type": "trigger",
                "data": {"nodeType": "manual.test_trigger", "config": {}},
                "position": {"x": 0, "y": 0},
            }
        ],
        "edges": [],
    }
    assert admin_service.compute_workflow_purpose(graph) is None
