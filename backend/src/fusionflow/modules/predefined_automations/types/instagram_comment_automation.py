"""`instagram.comment_automation` — the flagship predefined automation for
Instagram: reply (publicly and/or via DM) and/or hide a comment when its
text matches a configured keyword. Mirrors the Profiterasoft reference
wizard's "Setup Social Automation" screen this task was built against.

Config shape (the wizard's own structured answers, stored verbatim on
`PredefinedAutomation.config` for re-editing):
    {
      "trigger_keywords": ["price", "info"],       # non-empty, required
      "matching_method": "contains",                 # exact|contains|starts_with|ends_with
      "auto_hide": false,
      "reply_comment_text": "Check your DM!" | null, # public reply; null/empty disables it
      "dm_text": "Here are our prices..." | null,     # DM reply; null/empty disables it
    }

Deliberately scoped smaller than every toggle Profiterasoft's reference
screen shows - three of its five are not included here, on purpose, not by
oversight:
  - "Auto-Like" is not offered: confirmed against the real Graph API (not
    just this sandbox's stub) that Instagram has no "like a comment"
    endpoint at all - `POST /{comment_id}/likes` is a Facebook Page-comment
    capability, and 400s on `graph.instagram.com` every time. An earlier
    version of this file offered it; it never actually worked, and because
    the generated graph chains actions sequentially, a failing Auto-Like
    node was silently blocking the reply/DM actions after it in the same
    run - removed rather than left half-working.
  - "Requires Following" has no reliable backing in Instagram's public
    Graph API (there is no supported "does this arbitrary commenter follow
    my account" lookup) - it would either silently no-op or need scraping-
    adjacent behavior this codebase's stub-on-network-unreachable
    convention was never meant to paper over.
  - "Reply Delay" needs a wait/delay node type this workflow engine does
    not have yet (`flow_loop`/`flow_try_catch`/`flow_parallel` are the only
    container/timing-adjacent node types today) - a real fast-follow once
    one exists, not a permanent omission.
`auto_hide` IS included - a genuine, already-added `instagram/adapter.py`
capability (`hide_comment`, backed by the real `POST /{comment_id}?hide=`
endpoint).

Generated graph shape: trigger (`instagram.comment_received`) -> an
OR-chained sequence of `condition.field_compare` nodes (one per configured
keyword - see `graph_helpers.build_keyword_condition_chain`, which also
owns the "every keyword's `true` handle converges on the same target, the
last one's `false` handle terminates in a `log.noop`" wiring every
automation type in this package reuses) -> the enabled `connector.action`
nodes (one per toggle), chained sequentially - order doesn't matter
functionally since neither of hide/reply/DM depends on the others' output.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import build_keyword_condition_chain
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.comment_automation"

MatchingMethod = Literal["exact", "contains", "starts_with", "ends_with"]

_METHOD_TO_OPERATOR: dict[MatchingMethod, str] = {
    "exact": "eq",
    "contains": "contains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
}


class InstagramCommentAutomationConfig(BaseModel):
    trigger_keywords: list[str] = Field(default_factory=list)  # empty = match everything
    matching_method: MatchingMethod = "contains"
    auto_hide: bool = False
    reply_comment_text: str | None = None
    dm_text: str | None = None


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramCommentAutomationConfig.model_validate(config)
    instance_id = str(connector_instance_id)

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {"nodeType": "instagram.comment_received", "label": "Comment Received", "config": {}},
        }
    ]
    edges: list[dict[str, Any]] = []
    x = 780  # condition chain occupies x=260..~780 depending on keyword count; actions start past it

    action_nodes: list[dict[str, Any]] = []
    if parsed.auto_hide:
        action_nodes.append(
            {
                "id": "action-hide",
                "type": "action",
                "data": {
                    "nodeType": "connector.action",
                    "label": "Hide Comment",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "hide_comment",
                        "params": {"comment_id": "{{trigger.comment_id}}", "hidden": True},
                    },
                },
            }
        )
    if parsed.reply_comment_text:
        action_nodes.append(
            {
                "id": "action-reply",
                "type": "action",
                "data": {
                    "nodeType": "connector.action",
                    "label": "Reply to Comment",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "reply_to_comment",
                        "params": {"comment_id": "{{trigger.comment_id}}", "text": parsed.reply_comment_text},
                    },
                },
            }
        )
    if parsed.dm_text:
        action_nodes.append(
            {
                "id": "action-dm",
                "type": "action",
                "data": {
                    "nodeType": "connector.action",
                    "label": "Send DM",
                    "config": {
                        "connector_instance_id": instance_id,
                        # Private Reply (`recipient.comment_id`), not a
                        # generic send (`recipient.id`) - see
                        # `instagram/adapter.py::send_private_reply`'s
                        # docstring: it works on any comment up to 7 days
                        # old even with no prior open DM thread, which a
                        # first-time commenter never has.
                        "action": "send_private_reply",
                        "params": {"comment_id": "{{trigger.comment_id}}", "text": parsed.dm_text},
                    },
                },
            }
        )

    if not action_nodes:
        # A condition's `true` handle must still be wired to exactly one
        # edge even when the wizard enabled none of the four toggles - a
        # harmless `log.noop` is the "matched, but nothing configured to
        # do" terminal, same convention as the condition chain's own
        # "no keyword matched" terminal (see `graph_helpers.py`).
        action_nodes.append(
            {
                "id": "action-none",
                "type": "action",
                "data": {"nodeType": "log.noop", "label": "No Action Configured", "config": {}},
            }
        )

    # Action nodes are unrestricted (no declared output handles), so they
    # chain sequentially via plain default-handle edges - only the FIRST
    # one is the condition chain's convergence target.
    for offset, action_node in enumerate(action_nodes):
        action_node["position"] = {"x": x + offset * 260, "y": 0}
        nodes.append(action_node)
        if offset > 0:
            edges.append(
                {
                    "id": f"e-{action_nodes[offset - 1]['id']}-{action_node['id']}",
                    "source": action_nodes[offset - 1]["id"],
                    "target": action_node["id"],
                }
            )

    operator = _METHOD_TO_OPERATOR[parsed.matching_method]
    chain_nodes, chain_edges = build_keyword_condition_chain(
        trigger_node_id="trigger",
        field_path="trigger.text",
        keywords=parsed.trigger_keywords,
        operator=operator,
        on_match_target_id=action_nodes[0]["id"],
        start_x=260,
    )
    nodes.extend(chain_nodes)
    edges.extend(chain_edges)

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="instagram",
        label="Comment Automation",
        description=(
            "Reply, like, and/or hide comments on a post or reel when they match a keyword, "
            "and optionally send the commenter a DM."
        ),
        build_graph=build_graph,
    )
)
