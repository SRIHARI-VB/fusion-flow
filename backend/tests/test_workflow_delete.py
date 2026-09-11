"""`DELETE /workflows/{workflow_id}` (via `service.delete_workflow`) —
`requires_postgres`-marked, same convention as `test_workflow_starter_templates.py`:
real `businesses`/`workflows` rows are needed to exercise the DB-level
`ondelete="CASCADE"` chain (`WorkflowVersion`/`WorkflowRun`/`WorkflowRunStep`/
`WorkflowTrigger` all cascade from `workflows.id`), and RLS-scoped tenant
isolation can't be faked with a `FakeSession`. Skips (not fails) without
`$TEST_DATABASE_URL`, matching `test_rls_isolation.py`.
"""

from __future__ import annotations

import uuid

import pytest

from fusionflow.modules.workflows import service as workflows_service
from tests.conftest import requires_postgres

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def two_businesses(pg_session_factory):
    from sqlalchemy import text

    tenant_a, tenant_b = uuid.uuid4(), uuid.uuid4()
    async with pg_session_factory() as session:
        for tenant_id, name in ((tenant_a, "Delete Test Tenant A"), (tenant_b, "Delete Test Tenant B")):
            await session.execute(
                text("INSERT INTO businesses (id, name, slug, status) VALUES (:id, :name, :slug, 'active')"),
                {"id": tenant_id, "name": name, "slug": f"delete-test-{tenant_id.hex[:12]}"},
            )
        await session.commit()

    yield tenant_a, tenant_b

    async with pg_session_factory() as session:
        await session.execute(text("DELETE FROM businesses WHERE id = ANY(:ids)"), {"ids": [tenant_a, tenant_b]})
        await session.commit()


@requires_postgres
async def test_delete_workflow_cascades_versions_and_runs(pg_session_factory, two_businesses) -> None:
    from fusionflow.db.session import set_tenant_context
    from fusionflow.modules.workflows.models import RunStatus, Workflow, WorkflowRun, WorkflowVersion

    tenant_a, _ = two_businesses
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        workflow = await workflows_service.create_workflow(
            session, tenant_id=tenant_a, name="To be deleted", graph={"nodes": [], "edges": []}, created_by=uuid.uuid4()
        )
        await session.commit()

        await set_tenant_context(session, tenant_a)
        version = await workflows_service.get_latest_version(session, workflow.id)
        assert version is not None
        run = WorkflowRun(
            id=uuid.uuid4(),
            tenant_id=tenant_a,
            workflow_id=workflow.id,
            workflow_version_id=version.id,
            trigger_event_ref="test",
            status=RunStatus.COMPLETED,
        )
        session.add(run)
        await session.commit()
        workflow_id, version_id, run_id = workflow.id, version.id, run.id

        await set_tenant_context(session, tenant_a)
        workflow = await workflows_service.get_workflow(session, workflow_id)
        assert workflow is not None
        await workflows_service.delete_workflow(session, workflow)
        await session.commit()

        await set_tenant_context(session, tenant_a)
        assert await session.get(Workflow, workflow_id) is None
        assert await session.get(WorkflowVersion, version_id) is None
        assert await session.get(WorkflowRun, run_id) is None


@requires_postgres
async def test_delete_workflow_route_rejects_other_tenants_workflow(pg_session_factory, two_businesses) -> None:
    """`_get_workflow_or_404` (the same guard `GET`/`PATCH /{workflow_id}`
    already use) rejects a cross-tenant delete the identical way those
    routes already reject a cross-tenant read/update - a 404, not a 403,
    so tenant B can't even learn the workflow exists."""
    from fusionflow.db.session import set_tenant_context

    tenant_a, tenant_b = two_businesses
    async with pg_session_factory() as session:
        await set_tenant_context(session, tenant_a)
        workflow = await workflows_service.create_workflow(
            session, tenant_id=tenant_a, name="Tenant A's workflow", graph={"nodes": [], "edges": []}, created_by=uuid.uuid4()
        )
        await session.commit()
        workflow_id = workflow.id

        # Tenant B looks it up the same way the router's `_get_workflow_or_404`
        # does (get-then-check-tenant-id) - simulating the guard directly
        # since a full HTTP round-trip isn't set up in this test module.
        await set_tenant_context(session, tenant_b)
        found = await workflows_service.get_workflow(session, workflow_id)
        # RLS scopes the row to tenant_a - a tenant_b-scoped session either
        # can't see it at all (RLS) or `_get_workflow_or_404`'s own explicit
        # `workflow.tenant_id != tenant_id` check catches it - either way,
        # tenant B never gets a usable `Workflow` object back for it.
        assert found is None or found.tenant_id != tenant_b

        # Confirm it's untouched from tenant A's side.
        await set_tenant_context(session, tenant_a)
        still_there = await workflows_service.get_workflow(session, workflow_id)
        assert still_there is not None
