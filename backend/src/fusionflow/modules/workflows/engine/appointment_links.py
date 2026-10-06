"""Recover exact booking provenance from immutable successful workflow steps."""
from sqlalchemy import String, cast, select

from fusionflow.modules.workflows.models import StepStatus, WorkflowRun, WorkflowRunStep, WorkflowTriggerInbox, WorkflowVersion


async def booking_evidence(session, record, *, sender: str, connector_id=None, workflow_id=None):
    query = select(WorkflowRunStep, WorkflowRun, WorkflowVersion).join(
        WorkflowRun, WorkflowRunStep.workflow_run_id == WorkflowRun.id,
    ).join(WorkflowVersion, WorkflowRun.workflow_version_id == WorkflowVersion.id).join(
        WorkflowTriggerInbox, WorkflowRun.trigger_event_ref == cast(WorkflowTriggerInbox.id, String),
    ).where(
        WorkflowRunStep.tenant_id == record.tenant_id, WorkflowRun.tenant_id == record.tenant_id,
        WorkflowRunStep.status == StepStatus.SUCCEEDED,
        WorkflowVersion.tenant_id == record.tenant_id, WorkflowTriggerInbox.tenant_id == record.tenant_id,
        WorkflowTriggerInbox.event_type.in_(("instagram.message_received", "instagram.postback_received")),
        WorkflowTriggerInbox.payload["from"].astext == sender,
        WorkflowRunStep.output["item"]["id"].astext == str(record.id),
    )
    if connector_id is not None:
        query = query.where(WorkflowTriggerInbox.connector_instance_id == connector_id)
    if workflow_id is not None:
        query = query.where(WorkflowRun.workflow_id == workflow_id)
    matches = []
    for step, run, version in (await session.execute(query)).all():
        graph = version.compiled_graph or version.graph
        nodes = {n["id"]: n["data"] for n in graph["nodes"]}
        data = nodes.get(step.node_id, {})
        config = data.get("config", {})
        if (data.get("nodeType") in ("records.upsert", "module.create") and config.get("module") == "appointment"
                and config.get("operation", "create") == "create"):
            matches.append((step, run, graph, nodes))
    if len(matches) != 1:
        return None
    step, run, graph, nodes = matches[0]
    payload = dict(record.payload)
    # Older clinic versions put create_event immediately before the record
    # write. Follow that exact edge, never a name/date/phone coincidence.
    previous = [e["source"] for e in graph["edges"] if e["target"] == step.node_id]
    calendar_nodes = [n for n in previous if nodes[n].get("nodeType") == "connector.action"
                      and nodes[n].get("config", {}).get("action") == "create_event"]
    if calendar_nodes and not payload.get("calendar_event_id"):
        if len(calendar_nodes) != 1:
            return None
        node_id = calendar_nodes[0]
        event_steps = (await session.execute(select(WorkflowRunStep).where(
            WorkflowRunStep.tenant_id == record.tenant_id, WorkflowRunStep.workflow_run_id == run.id,
            WorkflowRunStep.node_id == node_id,
            WorkflowRunStep.status == StepStatus.SUCCEEDED,
        ))).scalars().all()
        event_ids = {s.output["id"] for s in event_steps if s.output and s.output.get("id")}
        if len(event_ids) != 1:
            return None
        payload["calendar_event_id"] = event_ids.pop()
        payload["calendar_connector_instance_id"] = nodes[node_id]["config"]["connector_instance_id"]
    return run.id, payload
