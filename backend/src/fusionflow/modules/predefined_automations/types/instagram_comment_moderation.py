"""`instagram.comment_moderation` — a smaller, purely-defensive sibling of
`instagram.comment_automation`: hide and/or delete a comment on this
account's own posts/reels when its text matches a configured keyword.

This is deliberately NOT about engagement - there is no reply/DM field at
all here, unlike `instagram_comment_automation.py`. That flagship is for
responding to genuine commenters; this one is for filtering out spam/abuse
before anyone has to see it. Keeping the two config shapes disjoint (rather
than folding `hide`/`delete` into the flagship as two more toggles) keeps
each wizard's "what does this automation actually do" story a single
sentence.

Config shape (the wizard's own structured answers, stored verbatim on
`PredefinedAutomation.config` for re-editing):
    {
      "trigger_keywords": ["buy followers", "http"],  # non-empty, required
      "matching_method": "contains",                   # exact|contains|starts_with|ends_with
      "hide": false,
      "delete": false,
    }

Generated graph shape: trigger (`instagram.comment_received`) -> an
OR-chained sequence of `condition.field_compare` nodes (one per configured
keyword - see `graph_helpers.build_keyword_condition_chain`) -> the enabled
`connector.action` nodes (one per toggle: `hide_comment`/`delete_comment`),
chained sequentially - order doesn't matter functionally since neither
action depends on the other's output. If neither toggle is enabled, falls
back to a single `log.noop` "no action configured" terminal, same
convention as `instagram_comment_automation.py`'s `build_graph`.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import build_keyword_condition_chain
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.comment_moderation"

MatchingMethod = Literal["exact", "contains", "starts_with", "ends_with"]

_METHOD_TO_OPERATOR: dict[MatchingMethod, str] = {
    "exact": "eq",
    "contains": "contains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
}


class InstagramCommentModerationConfig(BaseModel):
    trigger_keywords: list[str] = Field(default_factory=list)  # empty = match everything
    matching_method: MatchingMethod = "contains"
    hide: bool = False
    delete: bool = False


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramCommentModerationConfig.model_validate(config)
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
    if parsed.hide:
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
                        "params": {"comment_id": "{{trigger.comment_id}}"},
                    },
                },
            }
        )
    if parsed.delete:
        action_nodes.append(
            {
                "id": "action-delete",
                "type": "action",
                "data": {
                    "nodeType": "connector.action",
                    "label": "Delete Comment",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "delete_comment",
                        "params": {"comment_id": "{{trigger.comment_id}}"},
                    },
                },
            }
        )

    if not action_nodes:
        # A condition's `true` handle must still be wired to exactly one
        # edge even when the wizard enabled neither toggle - a harmless
        # `log.noop` is the "matched, but nothing configured to do"
        # terminal, same convention as the condition chain's own "no
        # keyword matched" terminal (see `graph_helpers.py`).
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
        label="Comment Moderation",
        description=(
            "Automatically hide or delete comments that match a keyword — for filtering spam or abuse, "
            "not for replying to genuine engagement (see 'Comment Automation' for that)."
        ),
        build_graph=build_graph,
    )
)
