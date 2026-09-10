"""One-shot, re-runnable live demonstration of every new Phase 4 piece
working together end-to-end, against the real database — not a seed
script (a demo *workflow* belongs to one specific tenant, unlike the
`workflow_node_templates` catalog seeded by `seed_workflow_node_templates.py`,
which this script assumes has already been run).

Builds one workflow for the "Srihari" tenant that exercises:
  - `flow.loop` iterating a synthetic `line_items` list, calling the
    `http_get_test_endpoint` WorkflowNodeTemplate (-> `http.request`) once
    per item against the real, public httpbin.org - proves per-iteration
    templating into a genuinely generic, code-free node, including a real
    outbound network call.
  - `flow.try_catch` wrapping the `send_whatsapp_template_message`
    WorkflowNodeTemplate (-> `connector.action`), both "success" and
    "error" handles wired - proves the WorkflowNodeTemplate -> generic
    executor -> real ConnectorAdapter.perform_action dispatch chain live.
    This environment has no WhatsApp app configured
    (`WHATSAPP_APP_ID`/`WHATSAPP_APP_SECRET` unset), so `send_text_message`
    always takes its documented stub-success path - this run exercises
    the "success" branch for real; the "error" branch (and the
    success/error mutual-exclusivity fix in flow_try_catch.py) is covered
    by dedicated failure-path unit tests in test_workflows_engine.py
    instead, since forcing a real failure here would need either editing
    global app config or a network-flakiness-dependent trick, neither of
    which belongs in a repeatable demo.
  - `condition.multi_branch` with 3 cases (large/medium/default->small).
  - One edge (classify "large" -> the Parallel container) carrying a
    `filter` in addition to its branch handle - proves edge filters stack
    with branch selection rather than replacing it (a "large" order under
    the filter's own threshold reaches `classify` but never reaches `par`).
  - `flow.parallel` with two trivial branches - proves the container
    architecture merges independent branch outputs.

Publishes the workflow (prints every validation issue, if any - the demo
is only meaningful if there are zero errors) and runs `simulate` against
four payloads chosen to hit every path: small order, medium order, large
order INSIDE the edge filter's threshold (Parallel fires), large order
OUTSIDE it (branch matched "large" but Parallel is skipped by the filter).

Confirmed live, end to end, on 2026-09-10 (see this phase's plan section,
Part E, for the full run transcript) — every scenario completed with the
expected steps and no unexpected failures.

--- Extending the node library later: the decision tree ---

This is the answer to "how do I add X to the automation engine" from now
on, so it never needs a fresh architecture discussion:

1. A new capability on an ALREADY-ADAPTED connector (e.g. WhatsApp gets a
   "send a template message" alongside today's "send text")?
   -> Add one branch to that adapter's own `perform_action` override
      (`modules/connectors/whatsapp/adapter.py`, see the pattern already
      there for `send_text_message`). Zero new node types, zero registry
      changes. Optionally add a `WorkflowNodeTemplate` row (pure admin
      data entry, see `seed_workflow_node_templates.py`) so it gets its
      own friendly palette entry instead of a raw `connector.action` node
      the author has to configure by hand.

2. A new THIRD-PARTY API that doesn't need real OAuth/webhook lifecycle?
   -> One `WorkflowNodeTemplate` row over `http.request` (see
      `http_get_test_endpoint` above for the exact shape). Zero backend
      code, ever. If it later needs a real connected-account lifecycle
      (OAuth, webhooks, credential storage), graduate it to a real
      `ConnectorAdapter` - `http.request` is deliberately the lightweight
      option, not a permanent substitute for the adapter framework.

3. A new comparison/branching variant?
   -> A new case in a `condition.multi_branch` node's own config (add a
      `{label, field_path, operator, value}` entry) - not a new node type.
      A genuinely new *operator* (beyond eq/neq/gt/gte/lt/lte/contains)
      is the one case that IS a small code change: add it to
      `engine/conditions.py`'s `_OPERATORS` dict, shared by
      `condition.field_compare`, `condition.multi_branch`, and edge
      filters all at once.

4. A new derived/reshaped value mid-flow?
   -> A new entry in a `data.transform` node's `outputs` config - not a
      new node type.

5. A new CONTROL-FLOW PRIMITIVE (genuinely new execution semantics, not
   just a new capability/API/comparison)?
   -> This is the one case that legitimately needs a new `NodeExecutor`
      subclass - Loop/TryCatch/Parallel are the only three today. Follow
      their pattern: set `can_contain_children = True` and a `child_role`
      if it needs to embed other nodes, use `ExecutionContext.run_children`
      to execute its body through the same step-recording/retry machinery
      as everything else (see `flow_loop.py` for the simplest example),
      and add it to `modules/workflows/nodes/__init__.py`'s import list.

Usage:
    python scripts/demo_phase4_proof_of_concept.py
"""

from __future__ import annotations

import asyncio
import uuid

from fusionflow.db import models as _models  # noqa: F401 - ORM registration side effect
from fusionflow.db.session import async_session_factory, set_tenant_context
from fusionflow.modules.connectors.models import ConnectorInstance, ConnectorState, ConnectorType
from fusionflow.modules.tenancy.models import Business, Membership
from fusionflow.modules.workflows import service as workflows_service
from fusionflow.modules.workflows.models import Workflow, WorkflowRunStep
from sqlalchemy import delete, select

DEMO_WORKFLOW_NAME = "Phase 4 proof of concept"

SRIHARI_BUSINESS_KEY = "Srihari"


def _node(node_id: str, node_type: str, config: dict | None = None, parent_id: str | None = None) -> dict:
    node: dict = {"id": node_id, "type": node_type, "data": {"nodeType": node_type, "config": config or {}}}
    if parent_id is not None:
        node["parentId"] = parent_id
    return node


def _edge(edge_id: str, source: str, target: str, source_handle: str | None = None, filter_: dict | None = None) -> dict:
    edge: dict = {"id": edge_id, "source": source, "target": target}
    if source_handle is not None:
        edge["sourceHandle"] = source_handle
    if filter_ is not None:
        edge["data"] = {"filter": filter_}
    return edge


def build_graph(whatsapp_instance_id: uuid.UUID) -> dict:
    return {
        "nodes": [
            _node("trigger", "manual.test_trigger"),
            _node("loop", "flow.loop", {"items_path": "{{trigger.line_items}}", "max_iterations": 5}),
            _node("http_call", "http_get_test_endpoint", parent_id="loop"),
            _node("guard", "flow.try_catch"),
            _node(
                "send_msg",
                "send_whatsapp_template_message",
                {
                    "connector_instance_id": str(whatsapp_instance_id),
                    "params": {"to": "+10000000000", "body": "Thanks for your order!"},
                },
                parent_id="guard",
            ),
            _node("on_error", "log.noop", {"message": "whatsapp send failed, caught by try/catch"}),
            _node(
                "classify",
                "condition.multi_branch",
                {
                    "cases": [
                        {"label": "large", "field_path": "trigger.amount", "operator": "gt", "value": 1000},
                        {"label": "medium", "field_path": "trigger.amount", "operator": "gt", "value": 100},
                    ],
                    "default_label": "small",
                },
            ),
            _node("branch_medium", "log.noop", {"message": "medium order"}),
            _node("branch_small", "log.noop", {"message": "small order"}),
            _node("par", "flow.parallel", {"wait_for": "all"}),
            _node("par_a", "log.noop", {"message": "parallel branch a"}, parent_id="par"),
            _node("par_b", "log.noop", {"message": "parallel branch b"}, parent_id="par"),
        ],
        "edges": [
            _edge("e1", "trigger", "loop"),
            _edge("e2", "loop", "guard"),
            _edge("e3", "guard", "on_error", source_handle="error"),
            # Both handles wired (see flow_try_catch.py's fixed logic):
            # this environment has no real WhatsApp app configured
            # (WHATSAPP_APP_ID unset), so send_text_message always takes
            # its documented stub-success path - this run exercises
            # guard's "success" branch for real, while "error" stays
            # correctly configured-but-dormant (already covered by
            # dedicated failure-path unit tests in test_workflows_engine.py).
            _edge("e4", "guard", "classify", source_handle="success"),
            # "large" branch ALSO requires amount > 5000 via an edge filter
            # stacked on top of the branch handle - large orders between
            # 1000 and 5000 are classified "large" but never reach `par`.
            _edge(
                "e5",
                "classify",
                "par",
                source_handle="large",
                filter_={"field_path": "trigger.amount", "operator": "gt", "value": 5000},
            ),
            _edge("e6", "classify", "branch_medium", source_handle="medium"),
            _edge("e7", "classify", "branch_small", source_handle="small"),
        ],
    }


async def main() -> None:
    async with async_session_factory() as session:
        business = (
            await session.execute(select(Business).where(Business.name == SRIHARI_BUSINESS_KEY))
        ).scalar_one()
        await set_tenant_context(session, business.id)
        membership = (
            await session.execute(select(Membership).where(Membership.business_id == business.id))
        ).scalars().first()
        user_id = membership.user_id  # created_by/published_by FK real users.id - a random UUID would violate the FK

        # Re-runnable: clean up any workflow left behind by a prior run of
        # this script (WorkflowVersion/WorkflowRun/WorkflowRunStep/
        # WorkflowTrigger all cascade-delete via their own FK ondelete).
        await session.execute(
            delete(Workflow).where(Workflow.tenant_id == business.id, Workflow.name == DEMO_WORKFLOW_NAME)
        )
        await session.commit()
        await set_tenant_context(session, business.id)

        # A real connector reference is required to pass publish
        # validation rule 2 (disconnected_connector_reference is a hard
        # error for a nonexistent instance, not just a soft warning) -
        # create one minimal WhatsApp instance for this demo if the
        # tenant doesn't already have one.
        whatsapp_type = (
            await session.execute(select(ConnectorType).where(ConnectorType.key == "whatsapp"))
        ).scalar_one()
        whatsapp_instance = (
            await session.execute(
                select(ConnectorInstance).where(
                    ConnectorInstance.tenant_id == business.id,
                    ConnectorInstance.connector_type_id == whatsapp_type.id,
                )
            )
        ).scalars().first()
        if whatsapp_instance is None:
            whatsapp_instance = ConnectorInstance(
                id=uuid.uuid4(),
                tenant_id=business.id,
                connector_type_id=whatsapp_type.id,
                state=ConnectorState.CONNECTED,
                display_name="Demo WhatsApp (Phase 4 proof of concept)",
            )
            session.add(whatsapp_instance)
            await session.commit()
            await set_tenant_context(session, business.id)
            print(f"created connector instance {whatsapp_instance.id}")
        else:
            print(f"reusing existing connector instance {whatsapp_instance.id}")

        workflow = await workflows_service.create_workflow(
            session,
            tenant_id=business.id,
            name=DEMO_WORKFLOW_NAME,
            graph=build_graph(whatsapp_instance.id),
            created_by=user_id,
        )
        await session.commit()
        print(f"created workflow {workflow.id}")

        # `SET LOCAL` (what set_tenant_context issues) is transaction-
        # scoped - it does not survive the commit above, so it must be
        # re-applied before the next statement on this session.
        await set_tenant_context(session, business.id)
        _, version, result = await workflows_service.publish_workflow(session, workflow, published_by=user_id)
        await session.commit()
        print(f"publish valid={not result.has_errors}")
        for issue in result.issues:
            print(f"  [{issue.severity}] {issue.rule} ({issue.node_id}): {issue.message}")
        if result.has_errors:
            print("ABORTING - fix validation errors before simulating")
            return

        scenarios = [
            ("small order, 1 line item", {"amount": 50, "line_items": [{"sku": "a"}]}),
            ("medium order, 2 line items", {"amount": 300, "line_items": [{"sku": "a"}, {"sku": "b"}]}),
            ("large order ABOVE filter threshold, 3 line items", {"amount": 6000, "line_items": [{"sku": "a"}, {"sku": "b"}, {"sku": "c"}]}),
            ("large order BELOW filter threshold (edge filter should skip Parallel)", {"amount": 2000, "line_items": []}),
        ]

        for label, payload in scenarios:
            print(f"\n--- scenario: {label} ---")
            await set_tenant_context(session, business.id)
            run = await workflows_service.simulate_workflow(session, workflow, payload=payload)
            # `run.steps` is a lazy relationship - AsyncSession can never
            # implicitly lazy-load it via plain attribute access (that
            # always raises MissingGreenlet), so query WorkflowRunStep
            # directly instead.
            status = run.status
            run_id = run.id
            steps = (
                await session.execute(
                    select(WorkflowRunStep)
                    .where(WorkflowRunStep.workflow_run_id == run_id)
                    .order_by(WorkflowRunStep.started_at)
                )
            ).scalars().all()
            printable = [
                (
                    s.node_id,
                    s.node_type,
                    s.status.value,
                    (s.input or {}).get("variables", {}).get("loop", {}).get("index"),
                    s.error,
                )
                for s in steps
            ]
            await session.commit()
            print(f"run status: {status}")
            for node_id, node_type, status_value, loop_idx, error in printable:
                suffix = f" (loop index={loop_idx})" if loop_idx is not None else ""
                print(f"  {node_id} [{node_type}] -> {status_value}{suffix}")
                if error:
                    print(f"      error: {error}")


if __name__ == "__main__":
    asyncio.run(main())
