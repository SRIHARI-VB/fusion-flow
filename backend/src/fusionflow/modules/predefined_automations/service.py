"""Predefined-automation domain logic.

The core idea (see the plan this task was built against): a predefined
automation is an ordinary `Workflow`/`WorkflowVersion` whose `graph` is
assembled server-side by a registered `build_graph` function (`registry.py`)
instead of hand-drawn on the canvas. Every function here delegates the
actual workflow lifecycle (create/update/publish/trigger-rebuild) to
`fusionflow.modules.workflows.service` - nothing here re-implements any of
that; this module only owns translating a wizard's `config` into a graph and
tracking which `PredefinedAutomation` row owns which generated `Workflow`.

None of these functions commit - routers own the transaction boundary,
matching every other module's convention in this codebase.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.connectors import service as connector_service
from fusionflow.modules.predefined_automations.models import PredefinedAutomation
from fusionflow.modules.predefined_automations.registry import registry
from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.models import Workflow, WorkflowStatus, WorkflowTrigger


class PredefinedAutomationError(Exception):
    """Domain-level failure. `status_code` is the HTTP status to emit -
    matches `connectors.service.ConnectorError`'s identical shape."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def _get_connector_instance_or_raise(
    session: AsyncSession, *, tenant_id: uuid.UUID, connector_instance_id: uuid.UUID, connector_type_key: str
):
    instance = await connector_service.get_instance(
        session, tenant_id=tenant_id, instance_id=connector_instance_id
    )
    if instance is None:
        raise PredefinedAutomationError(404, "Connector instance not found")
    if instance.connector_type.key != connector_type_key:
        raise PredefinedAutomationError(
            400,
            f"This automation type is for {connector_type_key!r}, not {instance.connector_type.key!r}",
        )
    return instance


async def create_predefined_automation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    connector_instance_id: uuid.UUID,
    automation_type: str,
    config: dict[str, Any],
    name: str,
    created_by: uuid.UUID,
) -> PredefinedAutomation:
    """Builds the graph, creates+publishes the underlying `Workflow`, and
    records the `PredefinedAutomation` row pointing at it. Raises
    `PredefinedAutomationError` if the generated graph fails publish
    validation (e.g. a required connector action param the wizard forgot
    to fill) - the caller should surface this as a 422, same as a
    connector's own `initiate_connect` rejection.
    """
    spec = registry.get_or_none(automation_type)
    if spec is None:
        raise PredefinedAutomationError(404, f"Unknown automation type: {automation_type!r}")

    await _get_connector_instance_or_raise(
        session, tenant_id=tenant_id, connector_instance_id=connector_instance_id, connector_type_key=spec.connector_type_key
    )

    graph = spec.build_graph(config, connector_instance_id)
    workflow = await workflows_service.create_workflow(
        session, tenant_id=tenant_id, name=name, graph=graph, created_by=created_by
    )

    automation = PredefinedAutomation(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        connector_instance_id=connector_instance_id,
        automation_type=automation_type,
        workflow_id=workflow.id,
        config=config,
        is_active=True,
    )
    session.add(automation)
    await session.flush()

    _, _, result = await workflows_service.publish_workflow(session, workflow, published_by=created_by)
    if result.has_errors:
        raise PredefinedAutomationError(
            422, f"Generated automation failed validation: {result.to_json()}"
        )
    return automation


async def update_predefined_automation(
    session: AsyncSession, automation: PredefinedAutomation, *, config: dict[str, Any], updated_by: uuid.UUID
) -> PredefinedAutomation:
    """Regenerates the graph from `config` and republishes - the wizard is
    always editing `config`, never the graph directly."""
    spec = registry.get(automation.automation_type)
    workflow = await workflows_service.get_workflow(session, automation.workflow_id)
    if workflow is None:
        raise PredefinedAutomationError(404, "Underlying workflow not found")

    graph = spec.build_graph(config, automation.connector_instance_id)
    await workflows_service.update_workflow(session, workflow, name=None, graph=graph, updated_by=updated_by)
    automation.config = config
    await session.flush()

    _, _, result = await workflows_service.publish_workflow(session, workflow, published_by=updated_by)
    if result.has_errors:
        raise PredefinedAutomationError(
            422, f"Generated automation failed validation: {result.to_json()}"
        )
    return automation


async def list_predefined_automations(
    session: AsyncSession, *, tenant_id: uuid.UUID, connector_type_key: str | None = None
) -> Sequence[PredefinedAutomation]:
    stmt = select(PredefinedAutomation).where(PredefinedAutomation.tenant_id == tenant_id)
    if connector_type_key is not None:
        # Join through connector_instances -> connector_types rather than
        # storing connector_type_key redundantly on this row - the instance
        # is already the source of truth for which provider it is.
        from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorType

        stmt = stmt.join(
            ConnectorInstance, ConnectorInstance.id == PredefinedAutomation.connector_instance_id
        ).join(ConnectorType, ConnectorType.id == ConnectorInstance.connector_type_id).where(
            ConnectorType.key == connector_type_key
        )
    stmt = stmt.order_by(PredefinedAutomation.created_at.desc())
    return (await session.execute(stmt)).scalars().all()


async def get_predefined_automation(
    session: AsyncSession, *, tenant_id: uuid.UUID, automation_id: uuid.UUID
) -> PredefinedAutomation | None:
    return (
        await session.execute(
            select(PredefinedAutomation).where(
                PredefinedAutomation.id == automation_id, PredefinedAutomation.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()


async def set_active(
    session: AsyncSession, automation: PredefinedAutomation, *, is_active: bool, actor_id: uuid.UUID
) -> PredefinedAutomation:
    """Pause: deletes the underlying workflow's `WorkflowTrigger` rows and
    archives it, so the outbox poller's trigger-dispatch lookup (which
    matches on `workflow_triggers`, not on this table - this module is
    invisible to the engine) stops finding it, without deleting the
    `Workflow`/`WorkflowVersion` or losing its `graph`/`config`. Resume:
    republishes (`workflows_service.publish_workflow` rebuilds
    `workflow_triggers` from the still-intact `graph` and flips the status
    back to `PUBLISHED`) - no `WorkflowStatus.PAUSED` state exists in this
    codebase (only draft/published/archived), so this is the closest
    faithful mapping onto what already exists rather than adding a new
    workflow-level status this module alone would understand.
    """
    workflow = await workflows_service.get_workflow(session, automation.workflow_id)
    if workflow is None:
        raise PredefinedAutomationError(404, "Underlying workflow not found")

    if is_active:
        _, _, result = await workflows_service.publish_workflow(session, workflow, published_by=actor_id)
        if result.has_errors:
            raise PredefinedAutomationError(422, f"Could not resume: {result.to_json()}")
    else:
        existing = (
            await session.execute(select(WorkflowTrigger).where(WorkflowTrigger.workflow_id == workflow.id))
        ).scalars().all()
        for row in existing:
            await session.delete(row)
        workflow.status = WorkflowStatus.ARCHIVED
        await session.flush()

    automation.is_active = is_active
    await session.flush()
    return automation


async def delete_predefined_automation(session: AsyncSession, automation: PredefinedAutomation) -> None:
    """Deletes both rows - `PredefinedAutomation.workflow_id` has no
    `ondelete` cascade the other direction, so the `Workflow` (and
    everything cascading from it: versions, runs, triggers) must be deleted
    explicitly here rather than relying on deleting this row alone to clean
    it up."""
    workflow = await workflows_service.get_workflow(session, automation.workflow_id)
    await session.delete(automation)
    if workflow is not None:
        await workflows_service.delete_workflow(session, workflow)
