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

from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.template_resolution import resolve_composite_branches
from fusionflow.modules.workflows.validation import validate_for_publish
from scripts.seed_workflow_starter_templates import (
    _APPOINTMENT_CANCELLATION_GRAPH,
    _APPOINTMENT_GRAPH,
    _APPOINTMENT_REQUIRED_OBJECT_TYPES,
    _FAQ_AUTORESPONDER_GRAPH,
    _FEEDBACK_GRAPH,
    _LEAD_CAPTURE_GRAPH,
    _MARKETING_OPTIN_GRAPH,
    _ORDER_CONFIRMATION_GRAPH,
    _ORDER_STATUS_GRAPH,
    _ORDERING_GRAPH,
    _PRODUCT_AVAILABILITY_GRAPH,
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
