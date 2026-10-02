"""`instagram.dm_automation` — auto-reply to an inbound Instagram direct
message when its text matches a configured keyword. Sibling to
`instagram_comment_automation.py`, same wizard-config-to-graph shape, but
triggered by `instagram.message_received` (a DM) instead of
`instagram.comment_received`.

Config shape:
    {
      "trigger_keywords": ["price", "hours"],  # [] = match every DM (see graph_helpers)
      "matching_method": "contains",             # exact|contains|starts_with|ends_with
      "reply_text": "Here are our hours...",     # required - the DM sent back
      "react_emoji": "love" | null,               # optional - react to the triggering message
      "reply_delay_minutes": 3 | null,            # optional - wait before replying (1..1440)
      "media_url": "https://..." | null,          # optional - attach an image/video
      "media_type": "image" | "video" | null,     # only meaningful when media_url is set
    }

Generated graph shape: trigger (`instagram.message_received`) -> the same
OR-chained `condition.field_compare` sequence
`graph_helpers.build_keyword_condition_chain` builds for the comment
automation -> optionally a `flow.delay` "Reply Delay" node -> a sequential
chain of `connector.action` nodes (same "unrestricted output handles chain
via plain edges" pattern `instagram_comment_automation.py` uses): the
always-present DM reply, then an optional media send, then an optional
message reaction - all three fire in the same run when configured, in that
order.
"""

from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field

from fusionflow.modules.predefined_automations.graph_helpers import build_keyword_condition_chain
from fusionflow.modules.predefined_automations.registry import PredefinedAutomationType, registry

AUTOMATION_TYPE = "instagram.dm_automation"

MatchingMethod = Literal["exact", "contains", "starts_with", "ends_with"]
ReactionEmoji = Literal["love", "like", "laugh", "wow", "sad", "angry"]

_METHOD_TO_OPERATOR: dict[MatchingMethod, str] = {
    "exact": "eq",
    "contains": "icontains",
    "starts_with": "starts_with",
    "ends_with": "ends_with",
}


class InstagramDmAutomationConfig(BaseModel):
    trigger_keywords: list[str] = Field(default_factory=list)  # empty = match everything
    matching_method: MatchingMethod = "contains"
    reply_text: str = Field(min_length=1)
    react_emoji: ReactionEmoji | None = Field(default=None)
    reply_delay_minutes: int | None = Field(default=None, ge=1, le=1440)
    media_url: str | None = Field(default=None)
    media_type: str | None = Field(default=None)


def build_graph(config: dict[str, Any], connector_instance_id: uuid.UUID) -> dict[str, Any]:
    parsed = InstagramDmAutomationConfig.model_validate(config)
    instance_id = str(connector_instance_id)

    nodes: list[dict[str, Any]] = [
        {
            "id": "trigger",
            "type": "trigger",
            "position": {"x": 0, "y": 0},
            "data": {"nodeType": "instagram.message_received", "label": "DM Received", "config": {}},
        }
    ]
    edges: list[dict[str, Any]] = []
    x = 780  # condition chain occupies x=260..~780 depending on keyword count; actions start past it

    # Always-present text reply, then the optional media send, then the
    # optional reaction - chained sequentially so all configured actions
    # fire in the same run (order doesn't matter functionally).
    action_nodes: list[dict[str, Any]] = [
        {
            "id": "action-reply",
            "type": "action",
            "data": {
                "nodeType": "connector.action",
                "label": "Reply via DM",
                "config": {
                    "connector_instance_id": instance_id,
                    "action": "send_direct_message",
                    "params": {"recipient_id": "{{trigger.from}}", "text": parsed.reply_text},
                },
            },
        }
    ]
    if parsed.media_url:
        action_nodes.append(
            {
                "id": "action-media",
                "type": "action",
                "data": {
                    "nodeType": "connector.action",
                    "label": "Send Media",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "send_media_message",
                        "params": {
                            "recipient_id": "{{trigger.from}}",
                            "media_url": parsed.media_url,
                            "media_type": parsed.media_type or "image",
                        },
                    },
                },
            }
        )
    if parsed.react_emoji:
        action_nodes.append(
            {
                "id": "action-react",
                "type": "action",
                "data": {
                    "nodeType": "connector.action",
                    "label": "React to Message",
                    "config": {
                        "connector_instance_id": instance_id,
                        "action": "react_to_message",
                        "params": {
                            "recipient_id": "{{trigger.from}}",
                            "message_id": "{{trigger.message_id}}",
                            "reaction": parsed.react_emoji,
                        },
                    },
                },
            }
        )

    # Action nodes are unrestricted (no declared output handles), so they
    # chain sequentially via plain default-handle edges - only the FIRST
    # one is the condition chain's (or the delay node's) target.
    delay_offset = 260 if parsed.reply_delay_minutes else 0
    for offset, action_node in enumerate(action_nodes):
        action_node["position"] = {"x": x + delay_offset + offset * 260, "y": 0}
        nodes.append(action_node)
        if offset > 0:
            edges.append(
                {
                    "id": f"e-{action_nodes[offset - 1]['id']}-{action_node['id']}",
                    "source": action_nodes[offset - 1]["id"],
                    "target": action_node["id"],
                }
            )

    on_match_target_id = action_nodes[0]["id"]
    if parsed.reply_delay_minutes:
        # "Reply Delay": inserted between the keyword-match chain and the
        # action chain - suspends the run for the configured minutes, then
        # auto-resumes straight into the first action node.
        nodes.append(
            {
                "id": "action-delay",
                "type": "action",
                "position": {"x": x, "y": 0},
                "data": {
                    "nodeType": "flow.delay",
                    "label": "Reply Delay",
                    "config": {"minutes": parsed.reply_delay_minutes},
                },
            }
        )
        edges.append(
            {
                "id": f"e-action-delay-{on_match_target_id}",
                "source": "action-delay",
                "target": on_match_target_id,
            }
        )
        on_match_target_id = "action-delay"

    operator = _METHOD_TO_OPERATOR[parsed.matching_method]
    chain_nodes, chain_edges = build_keyword_condition_chain(
        trigger_node_id="trigger",
        field_path="trigger.text",
        keywords=parsed.trigger_keywords,
        operator=operator,
        on_match_target_id=on_match_target_id,
        start_x=260,
    )
    nodes.extend(chain_nodes)
    edges.extend(chain_edges)

    return {"nodes": nodes, "edges": edges}


registry.register(
    PredefinedAutomationType(
        automation_type=AUTOMATION_TYPE,
        connector_type_key="instagram",
        label="DM Auto-Reply",
        description="Automatically reply to a direct message when its text matches a keyword.",
        build_graph=build_graph,
    )
)
