r"""Repair the clinic's ticket-based greeting and unmatched-postback fallback.

The latest ticket can be a diagnostic (or an internal clinical subject), so
it is not safe customer-facing greeting text. Reuse the existing returning
menu, and leave unmatched postbacks in the run log without a reply/ticket.
Existing tickets and immutable published versions are preserved.

Run from backend with its virtualenv and environment configured:

    python scripts/repair_clinic_instagram_workflow.py \
        --tenant-id UUID --workflow-id UUID --actor-email EMAIL \
        --expected-version 32

The default is a read-only validation. Review the result, then repeat with
--apply to publish one new version through the normal workflow service.
This script never executes the workflow or sends any messages.
"""

from __future__ import annotations

import argparse
import asyncio
from copy import deepcopy
import json
import uuid


class RepairError(ValueError):
    """The workflow no longer matches the reviewed repair."""


REMOVED_NODES = {
    "personalize-lookup-last-ticket": "records.get_latest",
    "personalize-cond-has-history": "condition.field_compare",
    "personalize-send-main-menu-returning": "connector.action",
    "reply-pb-fallback": "connector.action",
    "create-ticket-pb-fallback": "records.upsert",
    "note-pb-fallback": "tickets.add_note",
}
RETURNING_MENU = "send-main-menu-returning"
FIRST_TIME = "cond-first-time"
NO_MATCH = "pb-no-match"


def repair_graph(original: dict) -> dict:
    """Return a repaired copy; reject drift instead of guessing at routing."""
    graph = deepcopy(original)
    nodes = {node["id"]: node for node in graph["nodes"]}
    if len(nodes) != len(graph["nodes"]):
        raise RepairError("Duplicate node IDs")
    expected_types = {
        FIRST_TIME: "condition.field_compare",
        RETURNING_MENU: "connector.action",
        NO_MATCH: "log.noop",
    }
    present = set(REMOVED_NODES) & nodes.keys()
    if present and present != set(REMOVED_NODES):
        raise RepairError("Only part of the old fallback/personalization is present")
    if present:
        expected_types.update(REMOVED_NODES)
    for node_id, node_type in expected_types.items():
        if nodes.get(node_id, {}).get("data", {}).get("nodeType") != node_type:
            raise RepairError(f"Unexpected or missing node: {node_id}")

    if nodes[FIRST_TIME]["data"]["config"] != {
        "field_path": "find-or-create-customer-msg.created", "operator": "eq", "value": True,
    }:
        raise RepairError("First-time customer condition has changed")
    menu = nodes[RETURNING_MENU]["data"]["config"]
    if (menu.get("action") != "send_quick_replies"
            or menu.get("params", {}).get("text") != (
                "Welcome back! How may I help you today?\n\n"
                "(Or just type your answer if you don't see buttons.)"
            )):
        raise RepairError("Returning menu no longer has the reviewed greeting")

    affected = [edge for edge in graph["edges"] if (
        edge["source"] in REMOVED_NODES or edge["target"] in REMOVED_NODES
        or edge["source"] == NO_MATCH
        or (edge["source"] == FIRST_TIME and edge.get("sourceHandle") == "false")
    )]
    expected = {
        (FIRST_TIME, "personalize-lookup-last-ticket", "false"),
        ("personalize-lookup-last-ticket", "personalize-cond-has-history", None),
        ("personalize-cond-has-history", "personalize-send-main-menu-returning", "true"),
        ("personalize-cond-has-history", RETURNING_MENU, "false"),
        (NO_MATCH, "reply-pb-fallback", None),
        ("reply-pb-fallback", "create-ticket-pb-fallback", None),
        ("create-ticket-pb-fallback", "note-pb-fallback", None),
    } if present else {(FIRST_TIME, RETURNING_MENU, "false")}
    actual = {(e["source"], e["target"], e.get("sourceHandle")) for e in affected}
    if actual != expected or len(affected) != len(expected):
        raise RepairError("Unexpected connections to the affected branches")
    if any((e.get("data") or {}).get("filter") for e in affected):
        raise RepairError("Affected branches have additional edge filters")

    if present:
        # Preserve the existing false-branch edge's canvas metadata.
        branch = next(e for e in affected if e["source"] == FIRST_TIME)
        branch["target"] = RETURNING_MENU
        graph["nodes"] = [n for n in graph["nodes"] if n["id"] not in REMOVED_NODES]
        graph["edges"] = [e for e in graph["edges"]
                          if e["source"] not in REMOVED_NODES and e["target"] not in REMOVED_NODES]
    # Avoid leaving downstream templates or containment tied to deleted nodes.
    remaining = json.dumps({
        "nodes": graph["nodes"],
        "edge_data": [e.get("data") for e in graph["edges"]],
    })
    if any(node_id in remaining for node_id in REMOVED_NODES):
        raise RepairError("Remaining graph still references a removed node")
    return graph


async def repair_workflow(
    session, *, tenant_id: uuid.UUID, workflow_id: uuid.UUID,
    actor_email: str, expected_version: int, apply: bool = False,
) -> dict:
    """Stage the repair in the caller's transaction; never commit or execute."""
    from sqlalchemy import select
    from fusionflow.modules.auth.models import User
    from fusionflow.modules.tenancy.models import Membership, MembershipRole
    from fusionflow.modules.workflows import service
    from fusionflow.modules.workflows.models import Workflow, WorkflowStatus

    query = select(Workflow).where(Workflow.id == workflow_id, Workflow.tenant_id == tenant_id)
    if apply:
        query = query.with_for_update()
    workflow = (await session.execute(query)).scalar_one_or_none()
    if workflow is None or workflow.status != WorkflowStatus.PUBLISHED:
        raise RepairError("Target workflow is missing or is not published")
    version = await service.get_latest_version(session, workflow.id)
    if version is None or version.id != workflow.current_published_version_id or not version.published_at:
        raise RepairError("An unpublished draft exists; review it before repairing")
    if version.version_number != expected_version:
        raise RepairError("Published version changed; run a new dry run with the current version")
    actor_id = (await session.execute(
        select(User.id).join(Membership, Membership.user_id == User.id).where(
            User.email == actor_email,
            Membership.business_id == tenant_id,
            Membership.role.in_([MembershipRole.OWNER, MembershipRole.ADMIN]),
            Membership.accepted_at.is_not(None),
        )
    )).scalar_one_or_none()
    if actor_id is None:
        raise RepairError("Actor must be an owner or admin of the target tenant")

    candidate = repair_graph(version.graph)
    report = {
        "workflow_id": str(workflow.id), "previous_version": version.version_number,
        "changed": candidate != version.graph,
        "nodes_before": len(version.graph["nodes"]), "nodes_after": len(candidate["nodes"]),
    }
    if candidate == version.graph:
        return {**report, "result": "already repaired"}
    compiled = service.resolve_composite_branches(await service.resolve_node_templates(session, candidate))
    validation = await service.validate_for_publish(
        session, tenant_id=tenant_id, graph=service.WorkflowGraph.from_json(compiled),
    )
    if validation.has_errors:
        raise RepairError(f"Candidate failed publish validation: {validation.to_json()}")
    report["validation"] = validation.to_json()
    if not apply:
        return {**report, "result": "valid dry run; no writes"}

    await service.update_workflow(session, workflow, name=None, graph=candidate, updated_by=actor_id)
    _, published, validation = await service.publish_workflow(session, workflow, published_by=actor_id)
    if validation.has_errors:
        # Raising rolls back the entire caller-owned transaction, including
        # the new draft and trigger index if a future service changes ordering.
        raise RepairError(f"Publish failed validation: {validation.to_json()}")
    return {**report, "result": "published", "published_version": published.version_number,
            "published_version_id": str(published.id)}


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", type=uuid.UUID, required=True)
    parser.add_argument("--workflow-id", type=uuid.UUID, required=True)
    parser.add_argument("--actor-email", required=True)
    parser.add_argument("--expected-version", type=int, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from sqlalchemy import text
    from fusionflow.db import models as _models  # noqa: F401
    from fusionflow.db.session import async_session_factory, set_tenant_context

    async with async_session_factory() as session, session.begin():
        if not args.apply:
            await session.execute(text("SET TRANSACTION READ ONLY"))
        await set_tenant_context(session, args.tenant_id)
        report = await repair_workflow(session, **vars(args))
    # Emit success only after commit completes.
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
