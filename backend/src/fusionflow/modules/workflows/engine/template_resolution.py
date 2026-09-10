"""Compiles a graph's `WorkflowNodeTemplate`-backed nodes down to their
real, registered `base_node_type` + merged config, so the run loop and
publish-time validation never need to know templates exist at all — see
`modules.admin.models.WorkflowNodeTemplate`'s docstring and
`modules.workflows.nodes.connector_action`'s module docstring for the
full "catalog/config, not code" picture this is one piece of.

Two call sites, both in `service.py`:

* `publish_workflow` compiles once at publish time and persists the
  result onto `WorkflowVersion.compiled_graph` (the immutable artifact
  the engine actually executes — `outbox_poller.py` reads this, not
  `.graph`). `WorkflowVersion.graph` (the *authored* form, still
  referencing template keys) is left untouched, so editing a
  previously-published workflow keeps showing the friendly template
  identity instead of the generic executor it compiles to.
* `simulate_workflow` compiles transiently, in-memory only, on every
  call — a dry run always reflects whichever templates are active right
  now, even before the workflow is ever published.
"""

from __future__ import annotations

import copy
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from fusionflow.modules.admin import service as admin_service


async def resolve_node_templates(session: AsyncSession, graph_json: dict[str, Any] | None) -> dict[str, Any]:
    """Returns a *new* graph dict with every node whose `data.nodeType`
    matches an active `WorkflowNodeTemplate.key` rewritten to that
    template's `base_node_type`, with `config` = the template's
    `default_config` shallow-merged under the node's own `config` (the
    node instance's own values always win over the template default —
    the same "override, don't replace" precedent this codebase already
    uses for entitlement resolution). A node whose `nodeType` isn't a
    known template key is returned unchanged — this function is a no-op
    for a graph built entirely from raw registered node types.
    """
    if not graph_json:
        return dict(graph_json or {})

    templates = await admin_service.list_workflow_node_templates(session, active_only=True)
    by_key = {t.key: t for t in templates}
    if not by_key:
        return graph_json

    compiled = copy.deepcopy(graph_json)
    for node in compiled.get("nodes", []):
        data = node.get("data") or {}
        template = by_key.get(data.get("nodeType"))
        if template is None:
            continue
        data["nodeType"] = template.base_node_type
        data["config"] = {**(template.default_config or {}), **(data.get("config") or {})}
        node["data"] = data
    return compiled
