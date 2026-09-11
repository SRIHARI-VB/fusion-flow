"""Tests for the workflow-component system (composable-workflow-builder
redesign follow-up): admin-curated `WorkflowComponent` fragments plus a
tenant's own saved `WorkflowUserComponent` selections, merged into one
list by `workflows.service.list_components`.

Split the same way `test_workflow_starter_templates.py` is:

* Offline (default, no Postgres): every seeded fragment
  (`scripts/seed_workflow_components.py`) is a real graph fragment built
  from real node types - assert every node type resolves and its config
  validates, even though (unlike a full starter template) these fragments
  are deliberately left with dangling wiring/placeholders and are NOT run
  through full `validate_for_publish`.
* `requires_postgres`: `list_components`/create/delete/provisioning need
  real `businesses` rows and RLS-scoped tenant isolation - skips (not
  fails) without `$TEST_DATABASE_URL`, same as `test_rls_isolation.py`.
"""

from __future__ import annotations

import uuid

import pytest

from fusionflow.modules.workflows.engine.graph import WorkflowGraph
from fusionflow.modules.workflows.engine.registry import node_executor_registry
from scripts.seed_workflow_components import COMPONENTS
from tests.conftest import requires_postgres

# ---------------------------------------------------------------------------
# Offline: every seeded fragment is built from real, valid node config
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", COMPONENTS, ids=[c["key"] for c in COMPONENTS])
def test_seeded_component_fragment_uses_real_valid_node_types(spec: dict) -> None:
    graph = WorkflowGraph.from_json(spec["graph_fragment"])
    assert graph.nodes, f"component {spec['key']!r} has no nodes"
    for node in graph.nodes:
        executor = node_executor_registry.get(node.data.node_type)
        assert executor is not None, f"component {spec['key']!r} node {node.id!r} has unknown type {node.data.node_type!r}"
        # Deliberately not `validate_for_publish` - these fragments are
        # partial by design (dangling handles, placeholder tokens like
        # "{{YOUR_ORDER_NODE_ID.order_id}}"), which is expected, not an
        # error. Placeholder strings are still syntactically valid
        # non-empty strings, so per-node config validation should pass
        # cleanly regardless.
        executor.validate_config(node.data.config)


# ---------------------------------------------------------------------------
# requires_postgres: list/create/delete + isolation + provisioning
# ---------------------------------------------------------------------------


@pytest.fixture
async def two_businesses(pg_session_factory):
    from sqlalchemy import text

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    async with pg_session_factory() as session:
        for tenant_id, name in ((tenant_a, "Component Tenant A"), (tenant_b, "Component Tenant B")):
            await session.execute(
                text("INSERT INTO businesses (id, name, slug, status) VALUES (:id, :name, :slug, 'active')"),
                {"id": tenant_id, "name": name, "slug": f"component-{tenant_id.hex[:12]}"},
            )
        await session.commit()

    yield tenant_a, tenant_b

    async with pg_session_factory() as session:
        await session.execute(text("DELETE FROM businesses WHERE id = ANY(:ids)"), {"ids": [tenant_a, tenant_b]})
        await session.commit()


@pytest.fixture
async def rating_component(pg_session_factory):
    """A real admin `WorkflowComponent` row using the actual seeded
    post-purchase-rating fragment + its `required_object_types` spec -
    exercises the real provisioning path, not a synthetic one."""
    from fusionflow.modules.admin import service as admin_service

    spec = next(c for c in COMPONENTS if c["key"] == "post_purchase_rating")
    async with pg_session_factory() as session:
        component = await admin_service.create_workflow_component(
            session,
            key=f"test-{spec['key']}-{uuid.uuid4().hex[:8]}",
            name=spec["name"],
            description=spec["description"],
            category=spec["category"],
            icon=spec["icon"],
            graph_fragment=spec["graph_fragment"],
            required_object_types=spec["required_object_types"],
            is_active=True,
        )
        await session.commit()
        component_id = component.id

    yield component_id

    async with pg_session_factory() as session:
        await admin_service.delete_workflow_component(session, component_id)
        await session.commit()


@requires_postgres
async def test_list_components_merges_admin_and_user_and_isolates_by_tenant(
    pg_session_factory, two_businesses, rating_component
) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.workflows import schemas, service as workflows_service

    tenant_a, tenant_b = two_businesses

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        user_component = await workflows_service.create_user_component(
            session,
            tenant_id=tenant_a,
            payload=schemas.WorkflowComponentCreateRequest(
                name="My Own Snippet",
                description="A tenant-saved selection",
                category="Custom",
                icon=None,
                graph_fragment={"nodes": [], "edges": []},
            ),
        )
        await session.commit()

        entries_a = await workflows_service.list_components(session, tenant_id=tenant_a)

    admin_entries_a = [e for e in entries_a if e.source == "admin"]
    user_entries_a = [e for e in entries_a if e.source == "user"]
    assert any(e.id == str(rating_component) for e in admin_entries_a)
    assert any(e.id == str(user_component.id) and e.name == "My Own Snippet" for e in user_entries_a)

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_b)
        entries_b = await workflows_service.list_components(session, tenant_id=tenant_b)

    # Tenant B sees the same admin-curated components (global catalog) but
    # never tenant A's own saved component.
    assert any(e.id == str(rating_component) for e in entries_b if e.source == "admin")
    assert not any(e.id == str(user_component.id) for e in entries_b)


@requires_postgres
async def test_create_and_delete_user_component(pg_session_factory, two_businesses) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.workflows import schemas, service as workflows_service

    tenant_a, tenant_b = two_businesses

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        component = await workflows_service.create_user_component(
            session,
            tenant_id=tenant_a,
            payload=schemas.WorkflowComponentCreateRequest(
                name="Delete Me",
                description=None,
                category=None,
                icon=None,
                graph_fragment={"nodes": [], "edges": []},
            ),
        )
        await session.commit()
        component_id = component.id

        entries = await workflows_service.list_components(session, tenant_id=tenant_a)
        assert any(e.id == str(component_id) for e in entries)

    # A different tenant cannot delete it.
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_b)
        deleted_by_wrong_tenant = await workflows_service.delete_user_component(
            session, tenant_id=tenant_b, component_id=component_id
        )
        await session.commit()
    assert deleted_by_wrong_tenant is False

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        deleted = await workflows_service.delete_user_component(
            session, tenant_id=tenant_a, component_id=component_id
        )
        await session.commit()
    assert deleted is True

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        entries_after = await workflows_service.list_components(session, tenant_id=tenant_a)
    assert not any(e.id == str(component_id) for e in entries_after)


@requires_postgres
async def test_delete_user_component_cannot_delete_admin_component(
    pg_session_factory, two_businesses, rating_component
) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.workflows import service as workflows_service

    tenant_a, _ = two_businesses
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        deleted = await workflows_service.delete_user_component(
            session, tenant_id=tenant_a, component_id=rating_component
        )
        await session.commit()
    assert deleted is False


@requires_postgres
async def test_provision_component_creates_feedback_object_type_once(
    pg_session_factory, two_businesses, rating_component
) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.business_objects import service as business_objects_service
    from fusionflow.modules.workflows import service as workflows_service

    tenant_a, _ = two_businesses

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        found = await workflows_service.provision_component(
            session, tenant_id=tenant_a, component_id=str(rating_component)
        )
        await session.commit()
    assert found is True

    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        object_type = await business_objects_service.get_object_type_by_key(
            session, tenant_id=tenant_a, key="feedback"
        )
        assert object_type is not None
        field_defs = await business_objects_service.list_field_definitions(
            session, tenant_id=tenant_a, object_type_id=object_type.id
        )
        assert {f.key for f in field_defs} == {"rating", "comment", "order_id"}

    # Calling it again (e.g. a second workflow inserting the same
    # component) must not create a duplicate object type.
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        await workflows_service.provision_component(session, tenant_id=tenant_a, component_id=str(rating_component))
        await session.commit()

        await set_tenant_context(session, tenant_a)
        all_types = await business_objects_service.list_object_types(session, tenant_id=tenant_a)
        feedback_types = [t for t in all_types if t.key == "feedback"]
    assert len(feedback_types) == 1


@requires_postgres
async def test_provision_component_returns_false_for_unknown_id(pg_session_factory, two_businesses) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.workflows import service as workflows_service

    tenant_a, _ = two_businesses
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        found = await workflows_service.provision_component(
            session, tenant_id=tenant_a, component_id=str(uuid.uuid4())
        )
    assert found is False
